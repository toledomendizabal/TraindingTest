"""APScheduler service for scheduled tasks."""
import asyncio
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

        # Signal analysis every 10 seconds
        self.scheduler.add_job(
            self._run_signal_analysis,
            IntervalTrigger(seconds=10),
            id="signal_analysis",
            name="Signal Analysis",
            replace_existing=True
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

        # Weekly backtesting on Friday at 23:00
        self.scheduler.add_job(
            self._run_weekly_backtest,
            CronTrigger(day_of_week="fri", hour=23, minute=0),
            id="weekly_backtest",
            name="Weekly Backtesting",
            replace_existing=True
        )

        # Excel sync every 30 seconds
        self.scheduler.add_job(
            self._sync_excel,
            IntervalTrigger(seconds=30),
            id="excel_sync",
            name="Excel Sync",
            replace_existing=True
        )

        self.scheduler.start()
        self._is_running = True
        logger.info("Scheduler started with all jobs configured")

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
