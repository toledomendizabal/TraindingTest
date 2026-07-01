"""Signal engine for technical analysis and signal generation."""
import asyncio
from datetime import datetime
from typing import List, Dict, Optional
from loguru import logger

from app.models.signal import Signal, SignalDirection, SignalStatus
from app.services.market_data import market_data_service
from app.services.indicators import indicator_service
from app.services.excel_manager import excel_manager
from app.models.asset import Asset
from app.core.config import settings


class SignalEngine:
    """Engine for generating trading signals based on technical indicators."""

    # Default constants (can be overridden by Excel)
    MIN_INDICATORS_FOR_SIGNAL = 6
    SIGNAL_TIMEFRAME = "5m"

    def __init__(self):
        self.active_signals: Dict[str, Signal] = {}
        self.min_indicators = self.MIN_INDICATORS_FOR_SIGNAL
        self.signal_timeframe = self.SIGNAL_TIMEFRAME
        self._load_config_from_excel()
        self._load_active_signals()

    def _load_config_from_excel(self):
        """Load configuration from Excel file."""
        try:
            config = excel_manager.get_config()
            params = config.get("parameters", {})
            self.min_indicators = int(params.get("min_indicators", self.MIN_INDICATORS_FOR_SIGNAL))
            self.signal_timeframe = str(params.get("signal_timeframe", self.SIGNAL_TIMEFRAME))
            logger.info(f"Configuration loaded from Excel: Min Indicators={self.min_indicators}, Timeframe={self.signal_timeframe}")
        except Exception as e:
            logger.error(f"Error loading configuration from Excel: {e}")

    def _load_active_signals(self):
        """Load active signals from Excel into memory."""
        try:
            active_records = excel_manager.get_active_signals()
            for record in active_records:
                signal = Signal.from_dict(record)
                self.active_signals[signal.id] = signal
            logger.info(f"Loaded {len(self.active_signals)} active signals from Excel")
        except Exception as e:
            logger.error(f"Error loading active signals: {e}")

    async def analyze_asset(self, asset: str) -> Optional[Signal]:
        try:
            if self._has_active_signal(asset):
                logger.debug(f"[DEBUG] Active signal found for {asset}. Skipping new signal generation.")
                return None

            df = await market_data_service.get_time_series(
                asset, interval=self.signal_timeframe, outputsize=200
            )

            if df is None or df.empty:
                logger.debug(f"[DEBUG] No historical data (df) for {asset}. Skipping signal evaluation.")
                return None

            # CAMBIO 16: Filtro de spread máximo
            price_data = await market_data_service.get_price(asset)
            spread = 0.0
            if price_data and "ask" in price_data and "bid" in price_data:
                spread = price_data["ask"] - price_data["bid"]
            
            pip_info = Asset.get_pip_info(asset)
            pip_size = pip_info["pip_size"]
            current_spread_pips = round(spread / pip_size, 1)

            max_spread_pips = {
                "XAU": 50.0, # Aumentado para evitar bloqueos por spread en Oro
                "US30": 30.0,
                "US100": 30.0,
                "US500": 30.0,
                "DAX": 30.0,
                "GER40": 30.0,
                "DJI": 30.0,
                "NDX": 30.0,
                "SPX": 30.0,
            }.get(asset.upper().split("USD")[0], 10.0) # Default 10.0 for FX pairs

            if current_spread_pips > max_spread_pips:
                logger.info(f"Signal for {asset} rejected: Spread ({current_spread_pips} pips) exceeds max allowed ({max_spread_pips} pips).")
                logger.debug(f"[DEBUG] Skipping {asset}: Spread too high ({current_spread_pips} pips).")
                return None

            indicators = indicator_service.calculate_all(df)
            if not indicators:
                logger.debug(f"[DEBUG] No indicators calculated for {asset}. Skipping signal evaluation.")
                return None

            direction, indicators_met, details = indicator_service.evaluate_signals(df, indicators)
            
            # Fix "dejó de mandar señales": Usamos la configuración dinámica de Excel
            if direction == "NEUTRAL" or indicators_met < self.min_indicators:
                logger.debug(f"[DEBUG] Skipping {asset}: Indicator evaluation NEUTRAL or insufficient indicators met ({indicators_met}/{self.min_indicators}).")
                return None

            # Session Filter: Londres/Nueva York
            current_hour = datetime.utcnow().hour
            # Sesión institucional amplia para pruebas: 07:00 - 18:00 UTC
            if not (7 <= current_hour < 18):
                logger.info(f"Signal for {asset} rejected: Outside institutional sessions (London/NY). Current hour: {current_hour} UTC")
                return None

            # Volatility Filter: Avoid "Flat" markets
            if df is not None and len(df) > 50:
                recent_atr = df["high"].rolling(14).max() - df["low"].rolling(14).min()
                avg_atr = recent_atr.mean()
                current_atr = recent_atr.iloc[-1]
                
                if current_atr < (avg_atr * 0.5):
                    logger.info(f"Signal for {asset} rejected: Low volatility (Current ATR {round(current_atr/pip_size, 1)} < 50% of Avg {round(avg_atr/pip_size, 1)}).")
                    return None

                # Filter for high volatility (erratic markets) - Flexibilizado a 2.5x
                if current_atr > (avg_atr * 2.5): 
                    logger.info(f"Signal for {asset} rejected: High volatility (Current ATR {round(current_atr/pip_size, 1)} > 250% of Avg {round(avg_atr/pip_size, 1)}).")
                    return None

            # Validate with structural timeframe
            structural_confirmed = await self._validate_structural(asset, direction)
            if not structural_confirmed:
                logger.info(f"Signal for {asset} rejected: Failed structural validation.")
                logger.debug(f"[DEBUG] Skipping {asset}: Structural validation failed.")
                return None

            # If all checks pass, create the signal
            signal = self._create_signal(asset, direction, df, indicators_met)
            if signal:
                self.active_signals[signal.id] = signal
                await excel_manager.register_signal(signal)
                logger.info(f"NEW SIGNAL: {signal.asset} {signal.direction.value} @ {signal.entry_price}")
                return signal

        except Exception as e:
            logger.error(f"Error analyzing {asset}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
        
        return None

    async def analyze_all_assets(self) -> List[Signal]:
        """Analyze all active assets and return new signals."""
        new_signals = []
        for asset in settings.ACTIVE_ASSETS:
            signal = await self.analyze_asset(asset)
            if signal:
                new_signals.append(signal)
        return new_signals

    def _create_signal(self, asset: str, direction: str, df: pd.DataFrame, indicators_met: int) -> Optional[Signal]:
        """Create a new signal object with risk management parameters."""
        try:
            current_price = df["close"].iloc[-1]
            atr = indicator_service._calc_atr(df)
            
            # Risk Management
            risk_amount = settings.INITIAL_CAPITAL * (settings.RISK_PERCENTAGE / 100)
            
            # Stop Loss: 1.5 * ATR
            sl_distance = atr * 1.5
            if direction == "BUY":
                stop_loss = current_price - sl_distance
                tp_distance = sl_distance * 3 # 1:3 Risk Reward
                take_profit_1 = current_price + tp_distance
                take_profit_2 = current_price + (tp_distance * 1.5)
                take_profit_3 = current_price + (tp_distance * 2.0)
            else:
                stop_loss = current_price + sl_distance
                tp_distance = sl_distance * 3
                take_profit_1 = current_price - tp_distance
                take_profit_2 = current_price - (tp_distance * 1.5)
                take_profit_3 = current_price - (tp_distance * 2.0)

            # Calculate Lot Size
            pip_info = Asset.get_pip_info(asset)
            pip_size = pip_info["pip_size"]
            sl_pips = sl_distance / pip_size
            
            # Lot size formula: risk_amount / (sl_pips * pip_value_per_lot)
            # Simplification: risk_amount / (sl_distance * contract_size)
            contract_size = pip_info["contract_size"]
            lot_size = risk_amount / (sl_distance * contract_size)
            lot_size = round(max(0.01, lot_size), 2)

            # Create signal
            signal = Signal(
                asset=asset,
                direction=SignalDirection(direction),
                entry_price=float(current_price),
                stop_loss=float(stop_loss),
                take_profit_1=float(take_profit_1),
                take_profit_2=float(take_profit_2),
                take_profit_3=float(take_profit_3),
                lot_size=lot_size,
                timeframe=self.signal_timeframe,
                indicators_met=indicators_met,
                score=float(indicators_met / 18.0), # Normalized score
                session=market_data_service.get_current_session(),
                entry_hour=datetime.utcnow().hour,
                entry_spread=0.0, # Will be updated on execution
                entry_atr=float(atr)
            )
            
            return signal
        except Exception as e:
            logger.error(f"Signal creation error for {asset}: {e}")
            return None

    async def _validate_structural(self, asset: str, direction: str) -> bool:
        """Validate signal with higher timeframes (30m, 1h, 4h)."""
        try:
            confirmations = 0
            timeframes_evaluated = 0
            h4_confirmed = False
            
            for tf in ["30m", "1h", "4h"]:
                df_tf = await market_data_service.get_time_series(asset, interval=tf, outputsize=100)
                if df_tf is not None and not df_tf.empty:
                    timeframes_evaluated += 1
                    ema200 = df_tf["close"].ewm(span=200, adjust=False).mean().iloc[-1]
                    current_price = df_tf["close"].iloc[-1]
                    
                    is_confirmed = (direction == "BUY" and current_price > ema200) or \
                                   (direction == "SELL" and current_price < ema200)
                    
                    if is_confirmed:
                        confirmations += 1
                    
                    if tf == "4h" and is_confirmed:
                        h4_confirmed = True

            # Require at least 2 confirmations (e.g. 30m, 1h or 4h must align)
            if timeframes_evaluated > 0:
                if confirmations < 2:
                    logger.info(f"Structural validation: Insufficient trend confirmation ({confirmations}/2) for {asset}")
                    return False

            # SMC Alignment Check on 30m (Intermediate structure)
            df_30m = await market_data_service.get_time_series(asset, interval="30m", outputsize=100)
            if df_30m is not None:
                fvgs = indicator_service.detect_fvg(df_30m)
                # Look for a recent FVG (last 10 candles) in the trade direction
                recent_fvgs = fvgs[-10:] if len(fvgs) >= 10 else fvgs
                has_fvg = any(f["type"] == ("BULLISH" if direction == "BUY" else "BEARISH") for f in recent_fvgs)
                
                if not has_fvg:
                    logger.info(f"Signal for {asset} rejected: No {direction.lower()} FVG confirmation on 30m (last 10 candles).")
                    return False

            return True
        except Exception as e:
            logger.error(f"Error en validación estructural: {e}")
            return False

    def _has_active_signal(self, asset: str) -> bool:
        """Check if an asset already has an active signal to avoid duplicates."""
        # 1. Check memory for currently ACTIVE signals
        for signal in self.active_signals.values():
            if signal.asset == asset and signal.status == SignalStatus.ACTIVE:
                return True
        
        # 2. Check Excel for currently ACTIVE signals
        if excel_manager.has_active_signal(asset):
            return True
            
        # 3. ANTI-OVERTRADING: Cooldown Filter (5 minutes)
        try:
            df_signals = excel_manager.get_signals_dataframe()
            if not df_signals.empty:
                asset_signals = df_signals[df_signals["asset"] == asset].copy()
                if not asset_signals.empty:
                    asset_signals["closed_at"] = pd.to_datetime(asset_signals["closed_at"], errors="coerce")
                    last_close = asset_signals["closed_at"].max()
                    
                    if pd.notna(last_close):
                        diff_minutes = (datetime.now() - last_close).total_seconds() / 60
                        cooldown = 5 # 5 minutes cooldown
                        if diff_minutes < cooldown:
                            logger.info(f"Signal for {asset} rejected: Cooldown active ({round(cooldown - diff_minutes, 1)}m remaining).")
                            return True
        except Exception as e:
            logger.error(f"Error checking cooldown for {asset}: {e}")
            
        return False

    def get_active_signals(self) -> List[Signal]:
        """Get all active signals from memory."""
        return [s for s in self.active_signals.values() if s.status == SignalStatus.ACTIVE]


# Singleton instance
signal_engine = SignalEngine()
