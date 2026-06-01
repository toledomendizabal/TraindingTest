"""Signal generation engine - core trading logic."""
import uuid
from datetime import datetime
from typing import Optional, List, Dict
from loguru import logger
from app.core.config import settings
from app.models.signal import Signal, SignalDirection, SignalStatus
from app.models.asset import Asset, ASSET_CATALOG
from app.services.market_data import market_data_service
from app.services.indicators import indicator_service
from app.services.excel_manager import excel_manager


class SignalEngine:
    """Engine for generating trading signals based on 18 indicators confluence."""

    MIN_INDICATORS_FOR_SIGNAL = 6  # Minimum indicators for a valid signal
    ANALYSIS_TIMEFRAMES = ["30m", "1h"]  # Structural analysis
    SIGNAL_TIMEFRAME = "5m"  # Entry timeframe

    def __init__(self):
        self.active_signals: Dict[str, Signal] = {}
        self.min_indicators = self.MIN_INDICATORS_FOR_SIGNAL

    async def analyze_asset(self, asset: str) -> Optional[Signal]:
        """Analyze a single asset and generate signal if conditions are met."""
        try:
            # Check if asset already has an active signal
            if self._has_active_signal(asset):
                logger.bind(module="signals").info(f"{asset}: Active signal exists, skipping")
                return None

            # Get market data for signal timeframe
            df = await market_data_service.get_time_series(
                asset, interval=self.SIGNAL_TIMEFRAME, outputsize=200
            )

            if df is None or df.empty:
                logger.warning(f"No data available for {asset}")
                return None

            # Calculate all indicators
            indicators = indicator_service.calculate_all(df)

            if not indicators:
                return None

            # Evaluate signals
            direction, indicators_met, details = indicator_service.evaluate_signals(df, indicators)

            if direction == "NEUTRAL":
                return None

            if indicators_met < self.MIN_INDICATORS_FOR_SIGNAL:
                logger.bind(module="signals").debug(
                    f"{asset}: Only {indicators_met} indicators met (min: {self.MIN_INDICATORS_FOR_SIGNAL})"
                )
                return None

            # Validate with structural timeframe
            structural_confirmed = await self._validate_structural(asset, direction)
            if not structural_confirmed:
                logger.bind(module="signals").info(f"{asset}: Structural validation failed")
                return None

            # Generate signal
            current_price = df["close"].iloc[-1]
            atr_value = indicators.get("ATR", 0)

            signal = self._create_signal(
                asset=asset,
                direction=SignalDirection(direction),
                entry_price=current_price,
                atr=atr_value if atr_value else current_price * 0.001,
                indicators_met=indicators_met,
                details=details
            )

            if signal:
                self.active_signals[signal.id] = signal
                logger.bind(module="signals").info(
                    f"NEW SIGNAL: {signal.asset} {signal.direction.value} @ {signal.entry_price} "
                    f"SL: {signal.stop_loss} TP1: {signal.take_profit_1} "
                    f"Indicators: {signal.indicators_met}/18"
                )

            return signal

        except Exception as e:
            logger.error(f"Error analyzing {asset}: {e}")
            return None

    async def analyze_all_assets(self) -> List[Signal]:
        """Analyze all active assets and generate signals."""
        signals = []
        active_assets = settings.ACTIVE_ASSETS

        for asset in active_assets:
            signal = await self.analyze_asset(asset)
            if signal:
                signals.append(signal)
                # Register in Excel
                await excel_manager.register_signal(signal)

        return signals

    async def _validate_structural(self, asset: str, direction: str) -> bool:
        """Validate signal against higher timeframe structure."""
        try:
            for tf in self.ANALYSIS_TIMEFRAMES:
                df = await market_data_service.get_time_series(asset, interval=tf, outputsize=100)
                if df is None or df.empty:
                    continue

                # Check EMA 200 alignment on structural timeframe
                ema200 = df["close"].ewm(span=200, adjust=False).mean()
                current_price = df["close"].iloc[-1]

                if len(ema200) > 0:
                    if direction == "BUY" and current_price < ema200.iloc[-1]:
                        return False
                    elif direction == "SELL" and current_price > ema200.iloc[-1]:
                        return False

            return True
        except Exception:
            return True  # Allow signal if validation fails

    def _create_signal(
        self,
        asset: str,
        direction: SignalDirection,
        entry_price: float,
        atr: float,
        indicators_met: int,
        details: List[str]
    ) -> Optional[Signal]:
        """Create a complete signal with all parameters."""
        try:
            asset_info = ASSET_CATALOG.get(asset)
            if not asset_info:
                pip_info = Asset.get_pip_info(asset)
            else:
                pip_info = {
                    "pip_value": asset_info.pip_value,
                    "pip_size": asset_info.pip_size,
                    "contract_size": asset_info.contract_size
                }

            pip_size = pip_info["pip_size"]

            # Calculate Stop Loss using ATR (1.5x ATR)
            sl_distance = atr * 1.5

            if direction == SignalDirection.BUY:
                stop_loss = entry_price - sl_distance
                tp1 = entry_price + (sl_distance * 3)   # 1:3
                tp2 = entry_price + (sl_distance * 6)   # 1:6
                tp3 = entry_price + (sl_distance * 10)  # 1:10
            else:
                stop_loss = entry_price + sl_distance
                tp1 = entry_price - (sl_distance * 3)   # 1:3
                tp2 = entry_price - (sl_distance * 6)   # 1:6
                tp3 = entry_price - (sl_distance * 10)  # 1:10

            # Calculate pips
            sl_pips = abs(entry_price - stop_loss) / pip_size
            tp1_pips = abs(tp1 - entry_price) / pip_size
            tp2_pips = abs(tp2 - entry_price) / pip_size
            tp3_pips = abs(tp3 - entry_price) / pip_size

            # Calculate lot size: (Capital * Risk%) / (SL_pips * pip_value_per_lot)
            capital = settings.INITIAL_CAPITAL
            risk_pct = settings.RISK_PERCENTAGE / 100
            risk_amount = capital * risk_pct  # $30

            # Pip value per standard lot
            pip_value_per_lot = pip_size * pip_info["contract_size"]
            if pip_value_per_lot > 0 and sl_pips > 0:
                lot_size = risk_amount / (sl_pips * pip_value_per_lot)
            else:
                lot_size = 0.01

            # Round lot size
            lot_size = round(max(0.01, min(lot_size, 10.0)), 2)

            # Calculate score
            score = (indicators_met / 18) * 100

            signal = Signal(
                id=str(uuid.uuid4())[:8],
                asset=asset,
                direction=direction,
                entry_price=round(entry_price, 5),
                stop_loss=round(stop_loss, 5),
                take_profit_1=round(tp1, 5),
                take_profit_2=round(tp2, 5),
                take_profit_3=round(tp3, 5),
                sl_pips=round(sl_pips, 1),
                tp1_pips=round(tp1_pips, 1),
                tp2_pips=round(tp2_pips, 1),
                tp3_pips=round(tp3_pips, 1),
                lot_size=lot_size,
                timeframe=self.SIGNAL_TIMEFRAME,
                indicators_met=indicators_met,
                total_indicators=18,
                score=round(score, 1),
                status=SignalStatus.ACTIVE,
                session=market_data_service.get_current_session(),
                created_at=datetime.now(),
                indicators_detail=details
            )

            return signal

        except Exception as e:
            logger.error(f"Error creating signal for {asset}: {e}")
            return None

    def _has_active_signal(self, asset: str) -> bool:
        """Check if asset already has an active signal."""
        # Check in-memory signals
        for signal in self.active_signals.values():
            if signal.asset == asset and signal.status == SignalStatus.ACTIVE:
                return True

        # Check Excel records
        active_in_excel = excel_manager.has_active_signal(asset)
        return active_in_excel

    def get_active_signals(self) -> List[Signal]:
        """Get all active signals."""
        return [s for s in self.active_signals.values() if s.status == SignalStatus.ACTIVE]

    def get_all_signals(self) -> List[Signal]:
        """Get all signals."""
        return list(self.active_signals.values())


# Singleton instance
signal_engine = SignalEngine()
