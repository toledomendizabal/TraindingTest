"""APScheduler service for scheduled tasks."""
import asyncio
import os
import sys
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger
from app.core.config import settings


class SchedulerService:
    """Manages all scheduled tasks using APScheduler."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._is_running = False

    def start(self):
        """Start the scheduler with all configured jobs."""
        if self._is_running:
            return

        # Signal analysis every 60 seconds (Twelve Data free tier compliance)
        self.scheduler.add_job(
            self._run_signal_analysis,
            IntervalTrigger(seconds=60),
            id="signal_analysis",
            name="Signal Analysis",
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        # Daily test message at 9:00 AM
        self.scheduler.add_job(
            self._send_daily_test,
            CronTrigger(hour=9, minute=0),
            id="daily_test",
            name="Daily Test Message",
            replace_existing=True
        )

        # Daily backtesting at 23:59
        self.scheduler.add_job(
            self._run_daily_backtest,
            CronTrigger(hour=23, minute=59),
            id="daily_backtest",
            name="Daily Backtesting",
            replace_existing=True
        )

        # Weekly backtesting on Friday at 4:00 PM (16:00)
        self.scheduler.add_job(
            self._run_weekly_backtest,
            CronTrigger(day_of_week="fri", hour=16, minute=0),
            id="weekly_backtest",
            name="Weekly Backtesting",
            replace_existing=True
        )

        # Excel sync every 2 minutes
        self.scheduler.add_job(
            self._sync_excel,
            IntervalTrigger(minutes=2),
            id="excel_sync",
            name="Excel Sync",
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        # CAMBIO (motor de estrategias): revisión de "Señales por Confirmar"
        # (senales_por_confirmar.xlsx). Ver app/services/pending_signals_monitor.py.
        self.scheduler.add_job(
            self._check_pending_signals,
            IntervalTrigger(seconds=settings.PENDING_SIGNALS_CHECK_INTERVAL_SECONDS),
            id="pending_signals_check",
            name="Pending Signals Check (Señales por Confirmar)",
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        # KPIs diarios: se regenera daily_kpis.xlsx cada 15 minutos, para
        # que el día en curso se mantenga razonablemente al día en el
        # calendario del dashboard sin recalcular en cada request.
        self.scheduler.add_job(
            self._update_daily_kpis,
            IntervalTrigger(minutes=15),
            id="daily_kpis_refresh",
            name="Daily KPIs Refresh",
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        # Corte diario formal de KPIs a las 23:57 (justo antes del backtest
        # diario de las 23:59), para dejar el día ya cerrado con su
        # resultado final en daily_kpis.xlsx.
        self.scheduler.add_job(
            self._update_daily_kpis,
            CronTrigger(hour=23, minute=57),
            id="daily_kpis_close",
            name="Daily KPIs Close (corte diario)",
            replace_existing=True
        )

        # CAMBIO (a pedido del usuario, 2026-08-12): reinicio programado
        # del proceso cada PROCESS_RESTART_INTERVAL_HOURS (12h por
        # defecto), para evitar degradación acumulada de un proceso de
        # larga duración. Ver `_scheduled_restart` para el detalle de qué
        # hace antes de reiniciar (persistencia ya garantizada porque todo
        # el estado crítico vive en Excel, no en memoria).
        self.scheduler.add_job(
            self._scheduled_restart,
            IntervalTrigger(hours=settings.PROCESS_RESTART_INTERVAL_HOURS),
            id="scheduled_restart",
            name=f"Scheduled Restart (cada {settings.PROCESS_RESTART_INTERVAL_HOURS}h)",
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        # CAMBIO (a pedido del usuario, 2026-08-12): chequeo periódico de
        # que la conexión con MT5 siga viva, reconectando si se cayó --
        # ver mt5_executor.health_check(). Sin esto, una desconexión (caída
        # de red, reinicio de la terminal MT5, sesión expirada del bróker)
        # dejaba el sistema sin poder registrar operaciones en MT5 hasta el
        # próximo reinicio completo del proceso.
        self.scheduler.add_job(
            self._mt5_health_check,
            IntervalTrigger(minutes=settings.MT5_HEALTH_CHECK_INTERVAL_MINUTES),
            id="mt5_health_check",
            name="MT5 Connection Health Check",
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        # CAMBIO (a pedido del usuario, 2026-08-12): verificación periódica
        # de que las señales activas en memoria coincidan con Excel (ver
        # signal_engine.verify_persistence). Recupera automáticamente
        # cualquier señal "huérfana" (activa en Excel pero no en memoria) y
        # deja un log claro con el conteo de señales activas y pendientes.
        self.scheduler.add_job(
            self._verify_persistence,
            IntervalTrigger(minutes=settings.PERSISTENCE_CHECK_INTERVAL_MINUTES),
            id="persistence_check",
            name="Persistence Check (señales activas y pendientes)",
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        self.scheduler.start()
        self._is_running = True
        logger.info("Scheduler started with all jobs configured")

        # Verificación de persistencia inmediata al arrancar (además de la
        # periódica de arriba), para tener un reporte apenas inicia el
        # proceso -- especialmente útil justo después de un reinicio
        # programado, para confirmar en el log que nada se perdió.
        asyncio.create_task(self._verify_persistence())
        # Igual con la conexión MT5: intento de conectar/verificar
        # inmediato al arrancar, sin esperar al primer ciclo del job
        # periódico.
        asyncio.create_task(self._mt5_health_check())

    def stop(self):
        """Stop the scheduler."""
        if self._is_running:
            self.scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("Scheduler stopped")

    async def _run_signal_analysis(self):
        """Run signal analysis for all active assets."""
        try:
            from app.services.signal_engine import signal_engine
            signals = await signal_engine.analyze_all_assets()

            if signals:
                from app.services.telegram_service import telegram_service
                for signal in signals:
                    await telegram_service.send_signal_notification(signal)

        except Exception as e:
            logger.error(f"Error in signal analysis job: {e}")

    async def _send_daily_test(self):
        """Send daily test message via Telegram."""
        try:
            from app.services.telegram_service import telegram_service
            await telegram_service.send_test_message()
            logger.info("Daily test message sent")
        except Exception as e:
            logger.error(f"Error sending daily test: {e}")

    async def _run_daily_backtest(self):
        """Run daily backtesting."""
        try:
            from app.services.backtesting import backtesting_service
            result = await backtesting_service.run_daily_backtest()
            logger.info(f"Daily backtest completed: Win Rate {result.win_rate}%")

            # Send email report
            await self._send_backtest_email(result, "daily")

        except Exception as e:
            logger.error(f"Error in daily backtest: {e}")

    async def _run_weekly_backtest(self):
        """Run weekly backtesting."""
        try:
            from app.services.backtesting import backtesting_service
            result = await backtesting_service.run_weekly_backtest()
            logger.info(f"Weekly backtest completed: Win Rate {result.win_rate}%")

            # Send email report
            await self._send_backtest_email(result, "weekly")

        except Exception as e:
            logger.error(f"Error in weekly backtest: {e}")

    async def _sync_excel(self):
        """Sync Excel files."""
        try:
            from app.services.excel_manager import excel_manager
            # Ensure files are up to date
            excel_manager._ensure_files()
        except Exception as e:
            logger.error(f"Error syncing Excel: {e}")

    async def _check_pending_signals(self):
        """Revisa senales_por_confirmar.xlsx y activa/expira según corresponda."""
        try:
            from app.services.pending_signals_monitor import check_pending_signals
            await check_pending_signals()
        except Exception as e:
            logger.error(f"Error checking pending signals: {e}")

    async def _update_daily_kpis(self):
        """Regenera daily_kpis.xlsx con los KPIs (win rate, P/L neto, etc.) agrupados por día."""
        try:
            from app.services.excel_manager import excel_manager
            await excel_manager.update_daily_kpis_file()
        except Exception as e:
            logger.error(f"Error actualizando KPIs diarios: {e}")

    async def _mt5_health_check(self):
        """
        CAMBIO (a pedido del usuario, 2026-08-12): verifica que la conexión
        con MT5 siga viva y reconecta si hace falta. No hace nada si
        MT5_LIVE_TRADING_ENABLED está en False (modo "solo señales").
        """
        try:
            from app.services.mt5_executor import mt5_executor
            ok = mt5_executor.health_check()
            if settings.MT5_LIVE_TRADING_ENABLED:
                logger.debug(f"[MT5_HEALTH] Conexión {'OK' if ok else 'NO disponible'}.")
        except Exception as e:
            logger.error(f"Error en chequeo de salud de MT5: {e}")

    async def _verify_persistence(self):
        """
        CAMBIO (a pedido del usuario, 2026-08-12): verifica que las señales
        activas en memoria coincidan con Excel, y reporta cuántas señales
        "por confirmar" siguen pendientes. Ver
        signal_engine.verify_persistence() para el detalle.
        """
        try:
            from app.services.signal_engine import signal_engine
            signal_engine.verify_persistence()
        except Exception as e:
            logger.error(f"Error verificando persistencia: {e}")

    async def _scheduled_restart(self):
        """
        CAMBIO (a pedido del usuario, 2026-08-12): reinicio limpio del
        proceso cada `settings.PROCESS_RESTART_INTERVAL_HOURS` horas.

        Por qué es seguro: TODO el estado que importa (señales activas,
        señales por confirmar, configuración) ya vive en los archivos
        Excel, no en memoria -- se relee al arrancar
        (`signal_engine._load_active_signals`,
        `pending_signals_monitor` lee fresco cada ciclo). Este método
        primero hace un shutdown ordenado de las conexiones activas (MT5,
        cliente HTTP de Twelve Data, monitor de posiciones) para no dejar
        nada a medias, y solo entonces reinicia.

        Ver `settings.PROCESS_RESTART_MODE` para elegir entre
        auto-relanzado interno ("self_exec", sin necesitar supervisor
        externo) o solo terminar y dejar que un supervisor externo lo
        reinicie ("exit_only", recomendado si ya tienes uno configurado).
        """
        logger.warning(
            f"[REINICIO PROGRAMADO] Han pasado {settings.PROCESS_RESTART_INTERVAL_HOURS}h -- "
            f"iniciando reinicio limpio del proceso (modo: {settings.PROCESS_RESTART_MODE})."
        )
        try:
            # 1. Verificación de persistencia ANTES de reiniciar, para
            #    dejar constancia en el log de qué había activo justo
            #    antes del corte (útil para comparar contra lo que se
            #    recupera después del reinicio).
            from app.services.signal_engine import signal_engine
            pre_restart_report = signal_engine.verify_persistence()
            logger.warning(
                f"[REINICIO PROGRAMADO] Estado antes de reiniciar: "
                f"{pre_restart_report.get('active_in_memory', '?')} señal(es) activa(s), "
                f"{pre_restart_report.get('pending_confirmations', '?')} por confirmar. "
                f"Este estado ya está guardado en Excel y se recargará automáticamente "
                f"al volver a arrancar."
            )

            # 2. Shutdown ordenado de conexiones activas.
            from app.services.position_monitor import position_monitor
            from app.services.mt5_executor import mt5_executor
            from app.services.market_data import market_data_service
            from app.services.mt4_monitor import mt4_monitor

            await position_monitor.stop_monitoring()
            mt5_executor.disconnect()
            await mt4_monitor.stop()
            await market_data_service.close()
            self.stop()

        except Exception as e:
            logger.error(f"[REINICIO PROGRAMADO] Error durante el shutdown previo al reinicio: {e}")
            # Continúa con el reinicio de todas formas -- es preferible un
            # reinicio con un shutdown parcial a quedarse en un estado
            # potencialmente colgado indefinidamente.

        if settings.PROCESS_RESTART_MODE == "exit_only":
            logger.warning(
                "[REINICIO PROGRAMADO] Modo 'exit_only': el proceso va a terminar ahora. "
                "Asegúrate de tener un supervisor externo (systemd, NSSM, pm2, Task "
                "Scheduler, etc.) configurado para reiniciarlo automáticamente, o el "
                "backend quedará apagado hasta que alguien lo note."
            )
            sys.exit(0)
        else:
            logger.warning(
                f"[REINICIO PROGRAMADO] Relanzando el proceso ahora con el mismo comando "
                f"con el que se inició ({sys.executable} {' '.join(sys.argv)})..."
            )
            # os.execv reemplaza la imagen del proceso actual (mismo PID)
            # por una nueva ejecución de Python con los mismos argumentos
            # -- no requiere ningún supervisor externo. El proceso
            # arranca desde cero (nuevo event loop, nueva conexión MT5,
            # etc.) y recarga todo el estado desde Excel normalmente.
            os.execv(sys.executable, [sys.executable] + sys.argv)

    async def _send_backtest_email(self, result, report_type: str):
        """Send backtesting report via email."""
        try:
            from app.services.email_service import email_service
            await email_service.send_backtest_report(result, report_type)
        except Exception as e:
            logger.error(f"Error sending backtest email: {e}")

    def get_jobs_status(self) -> list:
        """Get status of all scheduled jobs."""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else "N/A",
                "trigger": str(job.trigger)
            })
        return jobs


# Singleton instance
scheduler_service = SchedulerService()
