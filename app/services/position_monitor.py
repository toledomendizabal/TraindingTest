"""Position monitoring service with accurate P/L and persistence."""
import asyncio
import pandas as pd
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
        # Wait a few seconds for MT4/MT5 to generate the initial CSV files
        logger.bind(module="monitoring").info("Waiting 5s for MetaTrader data to sync...")
        await asyncio.sleep(5)
        
        logger.bind(module="monitoring").info("Starting retroactive verification (Night-Watch)...")
        from app.services.signal_engine import signal_engine
        active_signals = signal_engine.get_active_signals()
        
        if not active_signals:
            logger.bind(module="monitoring").info("No active signals to verify.")
            return

        for signal in active_signals:
            try:
                logger.bind(module="monitoring").info(f"Checking history for {signal.asset} ({signal.id}) since {signal.created_at}")
                
                # Fetch up to 2000 M1 candles to cover up to 33 hours of offline time
                # Try with retries
                df = None
                for attempt in range(3):
                    df = await market_data_service.get_time_series(signal.asset, interval="1m", outputsize=2000)
                    if df is not None and not df.empty:
                        break
                    logger.bind(module="monitoring").warning(f"Attempt {attempt+1}: Could not fetch history for {signal.asset}. Retrying...")
                    await asyncio.sleep(2)
                
                if df is None or df.empty:
                    logger.bind(module="monitoring").error(f"Final failure fetching history for {signal.asset}. Skipping retroactive check.")
                    continue
                
                # Ensure datetime is comparable
                if not isinstance(df["datetime"].iloc[0], datetime):
                    df["datetime"] = pd.to_datetime(df["datetime"])
                
                # Filter data to only include candles AFTER signal creation
                # Add a small buffer of 1 minute to avoid entry candle
                df = df[df["datetime"] > signal.created_at]
                
                if df.empty:
                    logger.bind(module="monitoring").info(f"No new candles found for {signal.asset} since creation.")
                    continue

                logger.bind(module="monitoring").info(f"Analyzing {len(df)} candles for {signal.asset}...")

                # CAMBIO (fix win-rate): se reutiliza la misma cascada de
                # cierre parcial (SL -> TP1 parcial+BE -> TP2 parcial+SL@TP1
                # -> TP3 final) que usa el monitoreo en vivo, en vez de la
                # lógica anterior "todo o nada" que cerraba el 100% en el
                # primer nivel tocado. Como solo tenemos OHLC (no el camino
                # intra-vela), se evalúa de forma conservadora: primero SL,
                # luego TP3/TP2/TP1 usando el extremo favorable de la vela,
                # permitiendo varios eventos dentro de la misma vela si el
                # rango high-low los cubre.
                for _, row in df.iterrows():
                    high = float(row["high"])
                    low = float(row["low"])

                    # Una vela puede, en teoría, atravesar varios niveles
                    # (p. ej. un gap grande). Se procesa en cascada hasta que
                    # ningún nivel adicional se vea afectado por este rango.
                    for _ in range(4):  # máximo: SL/BE, TP1, TP2, TP3
                        if signal.id not in signal_engine.active_signals:
                            break  # ya se cerró del todo
                        cur = signal_engine.active_signals[signal.id]
                        if cur.status != SignalStatus.ACTIVE:
                            break

                        # Evaluamos primero el peor caso (SL) y luego el mejor (TP)
                        if cur.direction.value == "BUY":
                            sl_touched = low <= cur.stop_loss
                            tp_price = high
                        else:
                            sl_touched = high >= cur.stop_loss
                            tp_price = low

                        if sl_touched:
                            await self._evaluate_position(cur, cur.stop_loss)
                        else:
                            await self._evaluate_position(cur, tp_price)

                        # Si no hubo cambios de estado/lote en esta pasada, no
                        # tiene sentido seguir iterando esta misma vela.
                        if signal.id not in signal_engine.active_signals:
                            break
                        updated = signal_engine.active_signals[signal.id]
                        if updated.status != SignalStatus.ACTIVE:
                            break
                        if updated.remaining_lot_size == cur.remaining_lot_size:
                            break

                    if signal.id not in signal_engine.active_signals or \
                            signal_engine.active_signals[signal.id].status != SignalStatus.ACTIVE:
                        break  # señal totalmente cerrada, pasar a la siguiente
                        
            except Exception as e:
                logger.error(f"Error in retroactive verification for {signal.id}: {e}")
        
        logger.bind(module="monitoring").info("Retroactive verification completed.")

    async def stop_monitoring(self):
        self.is_running = False

    async def _check_positions(self):
        from app.services.signal_engine import signal_engine
        active_signals = signal_engine.get_active_signals()
        
        if not active_signals:
            # Occasionally check if Excel has signals that memory missed (safety net)
            if datetime.now().minute % 15 == 0: # Every 15 mins
                signal_engine._load_active_signals()
            return

        for signal in active_signals:
            asset = signal.asset
            # Try MT4 first (Offline)
            price_data = await market_data_service.get_price(asset)
            
            if price_data and "price" in price_data:
                await self._evaluate_position(signal, price_data["price"])
            else:
                logger.bind(module="monitoring").warning(f"No price data available for {asset} during monitoring.")

    async def _evaluate_position(self, signal, current_price: float):
        """
        Evalúa una posición activa contra SL/TP.

        CAMBIO (fix win-rate): ahora TP1/TP2/TP3 son niveles reales y
        distintos (1R/2R/3R). Se implementa cierre parcial escalonado:
          - TP1 alcanzado -> se cierra el % configurado (TP1_CLOSE_PCT) y el
            SL se mueve a breakeven (entry_price) para el resto de la
            posición. La operación NO se cierra del todo.
          - TP2 alcanzado -> se cierra otro % (TP2_CLOSE_PCT) y el SL sube a
            TP1, asegurando una ganancia mínima de 1R en lo que quede abierto.
          - TP3 alcanzado -> se cierra el resto de la posición. Estado final:
            CLOSED_TP3.
          - SL alcanzado ANTES de tocar TP1 -> pérdida total, CLOSED_SL.
          - SL (ya movido a breakeven o a TP1) alcanzado DESPUÉS de un cierre
            parcial -> el resultado neto ya no es una pérdida total: se marca
            como CLOSED_BE (o CLOSED_TP3 si el remanente ya estaba en TP1+).
        Esto es lo que efectivamente sube el win rate real: una operación que
        antes era 100% pérdida si revertía después de ir a favor, ahora deja
        una ganancia parcial materializada.
        """
        try:
            signal_id = signal.id
            asset = signal.asset
            direction = signal.direction.value
            entry_price = signal.entry_price
            tp1 = signal.take_profit_1
            tp2 = signal.take_profit_2
            tp3 = signal.take_profit_3

            pip_info = Asset.get_pip_info(asset)
            contract_size = pip_info["contract_size"]
            quote_currency = pip_info["quote_currency"]
            pip_size = pip_info["pip_size"]

            # Track Drawdown
            if direction == "BUY":
                floating_pips = (current_price - entry_price) / pip_size
            else:
                floating_pips = (entry_price - current_price) / pip_size
            if floating_pips < 0:
                drawdown = abs(floating_pips)
                if drawdown > signal.max_drawdown:
                    signal.max_drawdown = round(drawdown, 1)

            quote_to_usd_rate = await self._get_quote_to_usd_rate(quote_currency)

            def pnl_for(exit_price: float, lot: float) -> float:
                price_diff = (exit_price - entry_price) if direction == "BUY" else (entry_price - exit_price)
                return price_diff * lot * contract_size * quote_to_usd_rate

            # Init lot tracking on first evaluation if missing (legacy signals)
            if not signal.remaining_lot_size or signal.remaining_lot_size <= 0:
                signal.remaining_lot_size = signal.lot_size
            if not signal.initial_lot_size or signal.initial_lot_size <= 0:
                signal.initial_lot_size = signal.lot_size

            current_sl = signal.stop_loss

            sl_hit = (direction == "BUY" and current_price <= current_sl) or \
                     (direction == "SELL" and current_price >= current_sl)
            tp3_hit = (direction == "BUY" and current_price >= tp3) or \
                      (direction == "SELL" and current_price <= tp3)
            tp2_hit = (direction == "BUY" and current_price >= tp2) or \
                      (direction == "SELL" and current_price <= tp2)
            tp1_hit = (direction == "BUY" and current_price >= tp1) or \
                      (direction == "SELL" and current_price <= tp1)

            # --- 1. Stop Loss (inicial o ya movido a breakeven/TP1) ---
            if sl_hit:
                closing_lot = signal.remaining_lot_size
                leg_pnl = pnl_for(current_sl, closing_lot)
                total_pnl = round(signal.realized_partial_pnl + leg_pnl, 2)

                # Si ya hubo cierres parciales con ganancia, esto NO es una
                # pérdida total: es un breakeven o un cierre protegido.
                final_status = SignalStatus.CLOSED_SL
                if signal.tp1_hit:
                    final_status = SignalStatus.CLOSED_BE

                self._finalize_metrics(signal, current_sl)
                signal.remaining_lot_size = 0.0
                await self._close_position(signal_id, final_status, current_sl, total_pnl)
                return

            # --- 2. TP3: cierre final del remanente ---
            if tp3_hit:
                closing_lot = signal.remaining_lot_size
                leg_pnl = pnl_for(tp3, closing_lot)
                total_pnl = round(signal.realized_partial_pnl + leg_pnl, 2)

                self._finalize_metrics(signal, tp3)
                signal.remaining_lot_size = 0.0
                await self._close_position(signal_id, SignalStatus.CLOSED_TP3, tp3, total_pnl)
                return

            # --- 3. TP2: cierre parcial + SL sube a TP1 ---
            if tp2_hit and not signal.tp2_hit:
                close_pct = min(settings.TP2_CLOSE_PCT / 100.0, 1.0)
                closing_lot = round(signal.initial_lot_size * close_pct, 2)
                closing_lot = min(closing_lot, signal.remaining_lot_size)

                leg_pnl = pnl_for(tp2, closing_lot)
                signal.realized_partial_pnl = round(signal.realized_partial_pnl + leg_pnl, 2)
                signal.remaining_lot_size = round(signal.remaining_lot_size - closing_lot, 2)
                signal.lot_size = signal.remaining_lot_size
                signal.tp2_hit = True
                signal.stop_loss = tp1  # Asegura al menos 1R en el remanente
                signal.breakeven_active = True

                await excel_manager.register_partial_close(
                    signal_id, "TP2", tp2, closing_lot, leg_pnl, signal.remaining_lot_size
                )
                try:
                    from app.services.telegram_service import telegram_service
                    await telegram_service.send_partial_close_notification(
                        signal, "TP2", tp2, closing_lot, leg_pnl, signal.remaining_lot_size
                    )
                except Exception as e:
                    logger.error(f"Telegram partial-close notify error: {e}")

                logger.bind(module="monitoring").info(
                    f"PARTIAL CLOSE {signal_id} @ TP2 ({tp2}): closed {closing_lot} lots, "
                    f"P/L ${leg_pnl:.2f}, remaining {signal.remaining_lot_size} lots, SL->TP1"
                )
                return

            # --- 4. TP1: cierre parcial + SL a breakeven ---
            if tp1_hit and not signal.tp1_hit:
                close_pct = min(settings.TP1_CLOSE_PCT / 100.0, 1.0)
                closing_lot = round(signal.initial_lot_size * close_pct, 2)
                closing_lot = min(closing_lot, signal.remaining_lot_size)

                leg_pnl = pnl_for(tp1, closing_lot)
                signal.realized_partial_pnl = round(signal.realized_partial_pnl + leg_pnl, 2)
                signal.remaining_lot_size = round(signal.remaining_lot_size - closing_lot, 2)
                signal.lot_size = signal.remaining_lot_size
                signal.tp1_hit = True
                signal.stop_loss = entry_price  # Breakeven
                signal.breakeven_active = True

                await excel_manager.register_partial_close(
                    signal_id, "TP1", tp1, closing_lot, leg_pnl, signal.remaining_lot_size
                )
                try:
                    from app.services.telegram_service import telegram_service
                    await telegram_service.send_partial_close_notification(
                        signal, "TP1", tp1, closing_lot, leg_pnl, signal.remaining_lot_size
                    )
                except Exception as e:
                    logger.error(f"Telegram partial-close notify error: {e}")

                logger.bind(module="monitoring").info(
                    f"PARTIAL CLOSE {signal_id} @ TP1 ({tp1}): closed {closing_lot} lots, "
                    f"P/L ${leg_pnl:.2f}, remaining {signal.remaining_lot_size} lots, SL->breakeven"
                )
                return

        except Exception as e:
            logger.error(f"Evaluation error for {signal.id if hasattr(signal, 'id') else 'unknown'}: {e}")

    async def _get_quote_to_usd_rate(self, quote_currency: str) -> float:
        """Obtiene la tasa de conversión de la moneda cotizada a USD."""
        if quote_currency == "EUR":
            eurusd = await market_data_service.get_price("EURUSD")
            if eurusd:
                return eurusd["price"]
        elif quote_currency == "JPY":
            usdjpy = await market_data_service.get_price("USDJPY")
            if usdjpy:
                return 1.0 / usdjpy["price"]
        return 1.0

    def _finalize_metrics(self, signal, exit_price: float):
        """Calcula duración, hora de salida y R:R final antes del cierre."""
        signal.exit_hour = datetime.now().strftime("%H:%M")
        if signal.created_at:
            duration = (datetime.now() - signal.created_at).total_seconds() / 60
            signal.duration_minutes = round(duration, 1)

        pip_info = Asset.get_pip_info(signal.asset)
        pip_size = pip_info["pip_size"]
        risk_pips = signal.sl_pips if signal.sl_pips > 0 else 1
        gain_pips = abs(exit_price - signal.entry_price) / pip_size
        signal.risk_reward_ratio = round(gain_pips / risk_pips, 2)

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
            asset = signal_engine.active_signals[signal_id].asset if signal_id in signal_engine.active_signals else "Unknown"
            await telegram_service.send_close_notification(
                signal_id, status.value, close_price, profit_loss, asset
            )
        except Exception as e:
            logger.error(f"Telegram notify error: {e}")


position_monitor = PositionMonitor()
