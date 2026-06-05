"""Position monitoring service - tracks active signals against current prices."""
import asyncio
from datetime import datetime
from typing import Dict, List
from loguru import logger
from app.core.config import settings
from app.models.signal import SignalStatus, SignalDirection
from app.services.market_data import market_data_service
from app.services.excel_manager import excel_manager


class PositionMonitor:
    """Monitors active positions and checks for SL/TP hits."""

    def __init__(self):
        self.is_running = False
        self._monitor_interval = 1  # seconds

    async def start_monitoring(self):
        """Start the position monitoring loop."""
        self.is_running = True
        logger.bind(module="monitoring").info("Position monitor started")

        while self.is_running:
            try:
                await self._check_positions()
                await asyncio.sleep(self._monitor_interval)
            except Exception as e:
                logger.error(f"Error in position monitor: {e}")
                await asyncio.sleep(5)

    async def stop_monitoring(self):
        """Stop the position monitoring loop."""
        self.is_running = False
        logger.bind(module="monitoring").info("Position monitor stopped")

    async def _check_positions(self):
        """Check all active positions against current prices."""
        active_signals = excel_manager.get_active_signals()

        if not active_signals:
            return

        # Get current prices for all assets with active signals
        assets = list(set(s["asset"] for s in active_signals))
        prices = await market_data_service.get_multiple_prices(assets)

        for signal_data in active_signals:
            asset = signal_data["asset"]
            price_data = prices.get(asset)

            if not price_data:
                continue

            current_price = price_data["price"]
            await self._evaluate_position(signal_data, current_price)

    async def _evaluate_position(self, signal_data: Dict, current_price: float):
        """Evaluate a single position against current price."""
        try:
            signal_id = signal_data["id"]
            direction = signal_data["direction"]
            entry_price = float(signal_data["entry_price"])
            stop_loss = float(signal_data["stop_loss"])
            tp1 = float(signal_data["take_profit_1"])
            tp2 = float(signal_data["take_profit_2"])
            tp3 = float(signal_data["take_profit_3"])
            lot_size = float(signal_data["lot_size"])

            # Check Stop Loss
            if direction == "BUY":
                if current_price <= stop_loss:
                    profit_loss = (stop_loss - entry_price) * lot_size * 100000
                    await self._close_position(
                        signal_id, SignalStatus.CLOSED_SL, current_price, profit_loss
                    )
                    return

                # Check Take Profits (highest first)
                if current_price >= tp3:
                    profit_loss = (tp3 - entry_price) * lot_size * 100000
                    await self._close_position(
                        signal_id, SignalStatus.CLOSED_TP3, current_price, profit_loss
                    )
                elif current_price >= tp2:
                    profit_loss = (tp2 - entry_price) * lot_size * 100000
                    await self._close_position(
                        signal_id, SignalStatus.CLOSED_TP2, current_price, profit_loss
                    )
                elif current_price >= tp1:
                    profit_loss = (tp1 - entry_price) * lot_size * 100000
                    await self._close_position(
                        signal_id, SignalStatus.CLOSED_TP1, current_price, profit_loss
                    )

            elif direction == "SELL":
                if current_price >= stop_loss:
                    profit_loss = (entry_price - stop_loss) * lot_size * 100000
                    await self._close_position(
                        signal_id, SignalStatus.CLOSED_SL, current_price, profit_loss
                    )
                    return

                if current_price <= tp3:
                    profit_loss = (entry_price - tp3) * lot_size * 100000
                    await self._close_position(
                        signal_id, SignalStatus.CLOSED_TP3, current_price, profit_loss
                    )
                elif current_price <= tp2:
                    profit_loss = (entry_price - tp2) * lot_size * 100000
                    await self._close_position(
                        signal_id, SignalStatus.CLOSED_TP2, current_price, profit_loss
                    )
                elif current_price <= tp1:
                    profit_loss = (entry_price - tp1) * lot_size * 100000
                    await self._close_position(
                        signal_id, SignalStatus.CLOSED_TP1, current_price, profit_loss
                    )

        except Exception as e:
            logger.error(f"Error evaluating position {signal_data.get('id')}: {e}")

    async def _close_position(self, signal_id: str, status: SignalStatus,
                               close_price: float, profit_loss: float):
        """Close a position and update records."""
        logger.bind(module="monitoring").info(
            f"CLOSING {signal_id}: {status.value} @ {close_price} P/L: {profit_loss:.2f}"
        )

        # Update Signal Engine in-memory state
        from app.services.signal_engine import signal_engine
        if signal_id in signal_engine.active_signals:
            signal_engine.active_signals[signal_id].status = status

        # Update Excel
        await excel_manager.update_signal_status(
            signal_id, status.value, close_price, round(profit_loss, 2)
        )

        # Send Telegram notification
        try:
            from app.services.telegram_service import telegram_service
            await telegram_service.send_close_notification(
                signal_id, status.value, close_price, profit_loss
            )
        except Exception as e:
            logger.error(f"Error sending Telegram notification: {e}")


# Singleton instance
position_monitor = PositionMonitor()
