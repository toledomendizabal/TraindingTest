"""Position monitoring service with accurate P/L and persistence."""
import asyncio
from datetime import datetime
from typing import Dict, List
from loguru import logger
from app.core.config import settings
from app.models.signal import SignalStatus, SignalDirection
from app.models.asset import Asset, ASSET_CATALOG
from app.services.market_data import market_data_service
from app.services.excel_manager import excel_manager


class PositionMonitor:
    """Monitors active positions and checks for SL/TP hits."""

    def __init__(self):
        self.is_running = False
        self._monitor_interval = 1  # Always 1s now as we prioritize MT4

    async def start_monitoring(self):
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
        self.is_running = False

    async def _check_positions(self):
        from app.services.signal_engine import signal_engine
        active_signals = signal_engine.get_active_signals()
        
        if not active_signals:
            return

        for signal in active_signals:
            asset = signal.asset
            price_data = await market_data_service.get_price(asset)
            if price_data and "price" in price_data:
                await self._evaluate_position(signal, price_data["price"])

    async def _evaluate_position(self, signal, current_price: float):
        try:
            signal_id = signal.id
            asset = signal.asset
            direction = signal.direction.value
            entry_price = signal.entry_price
            stop_loss = signal.stop_loss
            tp1 = signal.take_profit_1
            tp2 = signal.take_profit_2
            tp3 = signal.take_profit_3
            lot_size = signal.lot_size

            pip_info = Asset.get_pip_info(asset)
            contract_size = pip_info["contract_size"]
            quote_currency = pip_info["quote_currency"]

            # Check SL/TP
            hit_status = None
            exit_price = None

            if direction == "BUY":
                if current_price <= stop_loss:
                    hit_status = SignalStatus.CLOSED_SL
                    exit_price = stop_loss
                elif current_price >= tp3:
                    hit_status = SignalStatus.CLOSED_TP3
                    exit_price = tp3
                elif current_price >= tp2:
                    hit_status = SignalStatus.CLOSED_TP2
                    exit_price = tp2
                elif current_price >= tp1:
                    hit_status = SignalStatus.CLOSED_TP1
                    exit_price = tp1
            else: # SELL
                if current_price >= stop_loss:
                    hit_status = SignalStatus.CLOSED_SL
                    exit_price = stop_loss
                elif current_price <= tp3:
                    hit_status = SignalStatus.CLOSED_TP3
                    exit_price = tp3
                elif current_price <= tp2:
                    hit_status = SignalStatus.CLOSED_TP2
                    exit_price = tp2
                elif current_price <= tp1:
                    hit_status = SignalStatus.CLOSED_TP1
                    exit_price = tp1

            if hit_status:
                # Calculate P/L accurately
                # P/L = (Exit - Entry) * LotSize * ContractSize * ConversionRate
                price_diff = (exit_price - entry_price) if direction == "BUY" else (entry_price - exit_price)
                
                quote_to_usd_rate = 1.0
                if quote_currency == "EUR":
                    eurusd = await market_data_service.get_price("EURUSD")
                    if eurusd: quote_to_usd_rate = eurusd["price"]
                elif quote_currency == "JPY":
                    usdjpy = await market_data_service.get_price("USDJPY")
                    if usdjpy: quote_to_usd_rate = 1.0 / usdjpy["price"]

                profit_loss = price_diff * lot_size * contract_size * quote_to_usd_rate
                
                await self._close_position(signal_id, hit_status, exit_price, profit_loss)

        except Exception as e:
            logger.error(f"Evaluation error for {signal_data.get('id')}: {e}")

    async def _close_position(self, signal_id: str, status: SignalStatus,
                               close_price: float, profit_loss: float):
        logger.bind(module="monitoring").info(
            f"CLOSING {signal_id}: {status.value} @ {close_price} P/L: ${profit_loss:.2f}"
        )

        from app.services.signal_engine import signal_engine
        if signal_id in signal_engine.active_signals:
            # Update status in memory
            signal_engine.active_signals[signal_id].status = status
            # Important: We keep it in active_signals for a moment to ensure UI/Excel update,
            # but it will be filtered out by get_active_signals() since its status is no longer ACTIVE.

        await excel_manager.update_signal_status(
            signal_id, status.value, close_price, round(profit_loss, 2)
        )

        try:
            from app.services.telegram_service import telegram_service
            await telegram_service.send_close_notification(
                signal_id, status.value, close_price, profit_loss
            )
        except Exception as e:
            logger.error(f"Telegram notify error: {e}")


position_monitor = PositionMonitor()
