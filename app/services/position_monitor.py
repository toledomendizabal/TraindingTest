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
        
        # 1. Retroactive verification on startup
        await self.verify_retroactive_signals()
        
        # 2. Continuous monitoring
        while self.is_running:
            try:
                await self._check_positions()
                await asyncio.sleep(self._monitor_interval)
            except Exception as e:
                logger.error(f"Error in position monitor: {e}")
                await asyncio.sleep(5)

    async def verify_retroactive_signals(self):
        """Verify if active signals hit TP/SL while the system was offline."""
        logger.bind(module="monitoring").info("Starting retroactive verification...")
        from app.services.signal_engine import signal_engine
        active_signals = signal_engine.get_active_signals()
        
        if not active_signals:
            return

        for signal in active_signals:
            try:
                # Get historical data since signal creation
                # We fetch the last 500 candles to cover the offline period
                df = await market_data_service.get_time_series(signal.asset, interval="1m", outputsize=500)
                if df is None or df.empty:
                    continue
                
                # Filter data to only include candles AFTER signal creation
                df = df[df["datetime"] >= signal.created_at]
                if df.empty:
                    continue
                
                # Check each candle for TP/SL hits
                for _, row in df.iterrows():
                    high = float(row["high"])
                    low = float(row["low"])
                    
                    hit_status = None
                    exit_price = None
                    
                    if signal.direction.value == "BUY":
                        if low <= signal.stop_loss:
                            hit_status = SignalStatus.CLOSED_SL
                            exit_price = signal.stop_loss
                        elif high >= signal.take_profit_3:
                            hit_status = SignalStatus.CLOSED_TP3
                            exit_price = signal.take_profit_3
                        elif high >= signal.take_profit_2:
                            hit_status = SignalStatus.CLOSED_TP2
                            exit_price = signal.take_profit_2
                        elif high >= signal.take_profit_1:
                            hit_status = SignalStatus.CLOSED_TP1
                            exit_price = signal.take_profit_1
                    else: # SELL
                        if high >= signal.stop_loss:
                            hit_status = SignalStatus.CLOSED_SL
                            exit_price = signal.stop_loss
                        elif low <= signal.take_profit_3:
                            hit_status = SignalStatus.CLOSED_TP3
                            exit_price = signal.take_profit_3
                        elif low <= signal.take_profit_2:
                            hit_status = SignalStatus.CLOSED_TP2
                            exit_price = signal.take_profit_2
                        elif low <= signal.take_profit_1:
                            hit_status = SignalStatus.CLOSED_TP1
                            exit_price = signal.take_profit_1
                            
                    if hit_status:
                        logger.bind(module="monitoring").info(
                            f"Retroactive hit detected for {signal.asset} ({signal.id}): {hit_status.value} at {row['datetime']}"
                        )
                        # Calculate P/L
                        pip_info = Asset.get_pip_info(signal.asset)
                        price_diff = (exit_price - signal.entry_price) if signal.direction.value == "BUY" else (signal.entry_price - exit_price)
                        
                        # Use simple conversion for retroactive (or fetch current)
                        profit_loss = price_diff * signal.lot_size * pip_info["contract_size"]
                        
                        await self._close_position(signal.id, hit_status, exit_price, profit_loss)
                        break # Signal closed, move to next
                        
            except Exception as e:
                logger.error(f"Error in retroactive verification for {signal.id}: {e}")
        
        logger.bind(module="monitoring").info("Retroactive verification completed.")

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
            pip_size = pip_info["pip_size"]

            # Track Drawdown
            if direction == "BUY":
                floating_pips = (current_price - entry_price) / pip_size
                if floating_pips < 0:
                    drawdown = abs(floating_pips)
                    if drawdown > signal.max_drawdown:
                        signal.max_drawdown = round(drawdown, 1)
            else:
                floating_pips = (entry_price - current_price) / pip_size
                if floating_pips < 0:
                    drawdown = abs(floating_pips)
                    if drawdown > signal.max_drawdown:
                        signal.max_drawdown = round(drawdown, 1)

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
                
                # Final metrics
                signal.exit_hour = datetime.now().strftime("%H:%M")
                if signal.created_at:
                    duration = (datetime.now() - signal.created_at).total_seconds() / 60
                    signal.duration_minutes = round(duration, 1)
                
                risk_pips = signal.sl_pips if signal.sl_pips > 0 else 1
                gain_pips = abs(exit_price - entry_price) / pip_size
                signal.risk_reward_ratio = round(gain_pips / risk_pips, 2)
                
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
