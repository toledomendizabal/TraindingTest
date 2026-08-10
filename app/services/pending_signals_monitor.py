"""
Monitor de 'Señales por Confirmar'.

Revisa periódicamente `excel/senales_por_confirmar.xlsx` (creado y
mantenido por `excel_manager`). Para cada fila PENDIENTE:

1. Si ya expiró (created_at + settings.PENDING_SIGNALS_EXPIRY_MINUTES),
   se marca EXPIRADA y no se activa nada.
2. Si no ha expirado, se vuelve a evaluar el activo con
   `strategy_engine.evaluate()`. Si la(s) estrategia(s) que faltaban ya
   confirman la MISMA dirección, la fila se marca CONFIRMADA y se llama
   DIRECTO a `signal_engine._finalize_signal()` -- ver CAMBIO CRÍTICO
   abajo -- para que la señal pase por el resto del pipeline (spread,
   sesión, estructura, macro, Excel principal, MT5).

CAMBIO CRÍTICO (fix, 2026-08-10): antes este monitor llamaba a
`signal_engine.analyze_asset(asset)` completo al confirmar, el cual vuelve
a invocar `strategy_engine.evaluate()` desde cero con datos recién
descargados. Para estrategias sensibles al último candle (ej. Estrategia 1
- Silver Bullet), esa segunda evaluación -- hecha 1-2 segundos después --
casi nunca coincidía con la confirmación recién detectada, y la señal se
rechazaba de inmediato con "ninguna estrategia confirmó dirección" justo
después de haberse marcado "CONFIRMADA". Confirmado con logs reales del
2026-08-09: las 2 únicas señales que llegaron a CONFIRMADA ese día
(USDCHF 22:00:18, AUDNZD 21:37:12) fueron rechazadas 1-2 segundos después
por esta causa -- 0 llegaron a `signals_tracking.xlsx` en todo el día.
Ahora se pasa la dirección YA confirmada (y el mismo `df` que la confirmó)
directo a `_finalize_signal()`, sin volver a preguntarle a
`strategy_engine`.

Uso: se agenda igual que el resto de tareas en `scheduler.py`, por
ejemplo cada `settings.PENDING_SIGNALS_CHECK_INTERVAL_SECONDS` segundos.
No reemplaza a `analyze_all_assets()` -- corre en paralelo, solo para las
señales que quedaron a medias.
"""
from datetime import datetime
from loguru import logger

from app.core.config import settings
from app.services.excel_manager import excel_manager
from app.services.market_data import market_data_service
from app.services.strategy_engine import strategy_engine


async def check_pending_signals():
    """Revisa todas las señales PENDIENTES y confirma o expira cada una."""
    pending_rows = excel_manager.get_open_pending_signals()
    if not pending_rows:
        return

    # Import diferido para evitar import circular (signal_engine importa excel_manager).
    from app.services.signal_engine import signal_engine

    now = datetime.now()
    checked = 0
    confirmed = 0
    expired = 0

    for row in pending_rows:
        checked += 1
        asset = row.get("asset")
        direction = row.get("direction")
        pending_id = row.get("id")

        try:
            expires_at = datetime.fromisoformat(row.get("expires_at"))
        except Exception:
            expires_at = None

        if expires_at and now >= expires_at:
            excel_manager.resolve_pending_signal(pending_id, "EXPIRADA")
            expired += 1
            logger.info(f"[PENDIENTE->EXPIRADA] {asset} {direction} (id={pending_id}): venció sin segunda confirmación.")
            continue

        if signal_engine._has_active_signal(asset):
            # Ya se abrió una señal para este activo por otra vía mientras
            # esta quedaba pendiente -- no tiene sentido finalizarla también.
            continue

        try:
            df = await market_data_service.get_time_series(
                asset, interval=getattr(settings, "SIGNAL_TIMEFRAME", "5m"),
                outputsize=200,
            )
        except Exception as e:
            logger.debug(f"[PENDIENTE] {asset}: no se pudo re-evaluar ({e}), se revisa en el próximo ciclo.")
            continue

        if df is None or df.empty:
            continue

        new_direction, strategies_confirmed, details, extra = strategy_engine.evaluate(asset, df)

        min_strategies = getattr(signal_engine, "min_strategies", 2)

        if new_direction == direction and strategies_confirmed >= min_strategies:
            excel_manager.resolve_pending_signal(pending_id, "CONFIRMADA")
            confirmed += 1
            logger.info(f"[PENDIENTE->CONFIRMADA] {asset} {direction} (id={pending_id}): segunda estrategia confirmó. Finalizando señal...")
            # CAMBIO CRÍTICO: se pasa la dirección YA confirmada y el mismo
            # `df` recién obtenido -- NO se vuelve a llamar a
            # strategy_engine.evaluate() por segunda vez (ver docstring).
            await signal_engine._finalize_signal(asset, new_direction, strategies_confirmed, details, df)
        elif new_direction not in (direction, "NEUTRAL"):
            # La dirección se invirtió por completo: ya no tiene sentido
            # mantenerla viva, se descarta como expirada.
            excel_manager.resolve_pending_signal(pending_id, "EXPIRADA")
            expired += 1
            logger.info(f"[PENDIENTE->EXPIRADA] {asset}: la dirección cambió de {direction} a {new_direction}, se descarta.")

    if checked:
        logger.info(f"[MONITOR PENDIENTES] Revisadas {checked} señal(es) por confirmar -> {confirmed} confirmada(s), {expired} expirada(s).")
