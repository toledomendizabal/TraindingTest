"""Signal generation engine with advanced risk management and Fibonacci levels."""
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

    MIN_INDICATORS_FOR_SIGNAL = 8
    ANALYSIS_TIMEFRAMES = ["30m", "1h"]
    SIGNAL_TIMEFRAME = "5m"

    def __init__(self):
        self.active_signals: Dict[str, Signal] = {}
        self.min_indicators = self.MIN_INDICATORS_FOR_SIGNAL
        self._load_active_signals()

    def _load_active_signals(self):
        """Load active signals from Excel on startup."""
        try:
            active_list = excel_manager.get_active_signals()
            for s_data in active_list:
                try:
                    # Convert dict to Signal model
                    signal = Signal(
                        id=s_data["id"],
                        asset=s_data["asset"],
                        direction=SignalDirection(s_data["direction"]),
                        entry_price=float(s_data["entry_price"]),
                        stop_loss=float(s_data["stop_loss"]),
                        take_profit_1=float(s_data["take_profit_1"]),
                        take_profit_2=float(s_data["take_profit_2"]),
                        take_profit_3=float(s_data["take_profit_3"]),
                        sl_pips=float(s_data["sl_pips"]),
                        tp1_pips=float(s_data["tp1_pips"]),
                        tp2_pips=float(s_data["tp2_pips"]),
                        tp3_pips=float(s_data["tp3_pips"]),
                        lot_size=float(s_data["lot_size"]),
                        timeframe=s_data["timeframe"],
                        indicators_met=int(s_data["indicators_met"]),
                        total_indicators=18,
                        score=float(s_data["score"]),
                        status=SignalStatus.ACTIVE,
                        session=s_data["session"],
                        created_at=datetime.fromisoformat(s_data["created_at"]) if s_data["created_at"] else datetime.now(),
                        indicators_detail=[]
                    )
                    self.active_signals[signal.id] = signal
                except Exception as e:
                    logger.error(f"Error parsing signal {s_data.get('id')}: {e}")
            
            if self.active_signals:
                logger.info(f"Loaded {len(self.active_signals)} active signals from Excel")
        except Exception as e:
            logger.error(f"Error loading active signals: {e}")

    async def analyze_asset(self, asset: str) -> Optional[Signal]:
        try:
            if self._has_active_signal(asset):
                return None

            df = await market_data_service.get_time_series(
                asset, interval=self.SIGNAL_TIMEFRAME, outputsize=200
            )

            if df is None or df.empty:
                return None

            indicators = indicator_service.calculate_all(df)
            if not indicators:
                return None

            direction, indicators_met, details = indicator_service.evaluate_signals(df, indicators)
            if direction == "NEUTRAL" or indicators_met < self.MIN_INDICATORS_FOR_SIGNAL:
                return None

            # Validate with structural timeframe
            structural_confirmed = await self._validate_structural(asset, direction)
            if not structural_confirmed:
                return None

            # Generate signal
            current_price = df["close"].iloc[-1]
            atr_value = indicators.get("ATR", 0)
            
            # Get current spread
            price_data = await market_data_service.get_price(asset)
            spread = 0.0
            if price_data and "ask" in price_data and "bid" in price_data:
                spread = abs(price_data["ask"] - price_data["bid"])

            signal = await self._create_signal(
                asset=asset,
                direction=SignalDirection(direction),
                entry_price=current_price,
                atr=atr_value if atr_value else current_price * 0.001,
                indicators_met=indicators_met,
                details=details,
                spread=spread
            )

            if signal:
                self.active_signals[signal.id] = signal
                await excel_manager.register_signal(signal)
                try:
                    from app.services.telegram_service import telegram_service
                    await telegram_service.send_signal_notification(signal)
                except Exception as e:
                    logger.error(f"Telegram error: {e}")

            return signal
        except Exception as e:
            logger.error(f"Error analyzing {asset}: {e}")
            return None

    async def _create_signal(
        self,
        asset: str,
        direction: SignalDirection,
        entry_price: float,
        atr: float,
        indicators_met: int,
        details: List[str],
        spread: float = 0.0
    ) -> Optional[Signal]:
        try:
            pip_info = Asset.get_pip_info(asset)
            pip_size = pip_info["pip_size"]
            contract_size = pip_info["contract_size"]
            quote_currency = pip_info["quote_currency"]

            # 1. Calculate Stop Loss using ATR (1.5x ATR)
            sl_distance = atr * 1.5
            
            # --- Apply Minimum Stop Loss Limits ---
            is_index_or_gold = any(x in asset.upper() for x in ["XAU", "US30", "US100", "US500", "DAX", "DJI", "NDX", "SPX"])
            is_ger40 = any(x in asset.upper() for x in ["GER40", "DAX"])
            is_gold = "XAU" in asset.upper()
            
            min_sl_pips = 300 if (is_index_or_gold and not is_ger40) else 6
            current_sl_pips = sl_distance / pip_size
            
            if current_sl_pips < min_sl_pips:
                sl_distance = min_sl_pips * pip_size

            # 2. Calculate Take Profit levels using Fibonacci Extensions (R:R equivalents)
            if direction == SignalDirection.BUY:
                stop_loss = entry_price - sl_distance
                tp1 = entry_price + (sl_distance * 3)
                tp2 = entry_price + (sl_distance * 6)
                tp3 = entry_price + (sl_distance * 10)
            else:
                stop_loss = entry_price + sl_distance
                tp1 = entry_price - (sl_distance * 3)
                tp2 = entry_price - (sl_distance * 6)
                tp3 = entry_price - (sl_distance * 10)

            # 3. Accurate Risk Management
            capital = settings.INITIAL_CAPITAL
            # Special risk for Gold: 0.75%, others 0.3%
            risk_pct = 0.75 if is_gold else settings.RISK_PERCENTAGE
            risk_amount_usd = capital * (risk_pct / 100)

            # Currency Conversion (Quote to USD)
            quote_to_usd_rate = 1.0
            if quote_currency == "EUR":
                # For GER40, we need EURUSD rate
                eurusd_data = await market_data_service.get_price("EURUSD")
                if eurusd_data:
                    quote_to_usd_rate = eurusd_data["price"]
            elif quote_currency == "JPY":
                usdjpy_data = await market_data_service.get_price("USDJPY")
                if usdjpy_data:
                    quote_to_usd_rate = 1.0 / usdjpy_data["price"]

            # Pip value in USD
            pip_value_usd = pip_info["pip_value"] * quote_to_usd_rate
            pip_value_per_lot = pip_value_usd * contract_size
            
            sl_pips = sl_distance / pip_size
            
            if pip_value_per_lot > 0 and sl_pips > 0:
                lot_size = risk_amount_usd / (sl_pips * pip_value_per_lot)
            else:
                lot_size = 0.01

            # Round lot size to 2 decimals
            lot_size = round(max(0.01, min(lot_size, 100.0)), 2)

            score = (indicators_met / 18) * 100

            return Signal(
                id=str(uuid.uuid4())[:8],
                asset=asset,
                direction=direction,
                entry_price=round(entry_price, 5),
                stop_loss=round(stop_loss, 5),
                take_profit_1=round(tp1, 5),
                take_profit_2=round(tp2, 5),
                take_profit_3=round(tp3, 5),
                sl_pips=round(sl_pips, 1),
                tp1_pips=round(abs(tp1 - entry_price) / pip_size, 1),
                tp2_pips=round(abs(tp2 - entry_price) / pip_size, 1),
                tp3_pips=round(abs(tp3 - entry_price) / pip_size, 1),
                lot_size=lot_size,
                timeframe=self.SIGNAL_TIMEFRAME,
                indicators_met=indicators_met,
                total_indicators=18,
                score=round(score, 1),
                status=SignalStatus.ACTIVE,
                session=market_data_service.get_current_session(),
                created_at=datetime.now(),
                entry_hour=datetime.now().strftime("%H:%M"),
                entry_spread=round(spread / pip_size, 1),
                entry_atr=round(atr / pip_size, 1),
                indicators_detail=details
            )
        except Exception as e:
            logger.error(f"Signal creation error for {asset}: {e}")
            return None

    async def analyze_all_assets(self) -> List[Signal]:
        signals = []
        for asset in settings.ACTIVE_ASSETS:
            signal = await self.analyze_asset(asset)
            if signal:
                signals.append(signal)
        return signals

    async def _validate_structural(self, asset: str, direction: str) -> bool:
        try:
            # Special Strategy for XAUUSD
            if "XAU" in asset.upper():
                df_5m = await market_data_service.get_time_series(asset, interval="5m", outputsize=300)
                if df_5m is not None and not df_5m.empty:
                    # 1. EMA 50 > EMA 200
                    ema50 = df_5m["close"].ewm(span=50, adjust=False).mean()
                    ema200 = df_5m["close"].ewm(span=200, adjust=False).mean()
                    
                    if direction == "BUY" and ema50.iloc[-1] <= ema200.iloc[-1]:
                        return False
                    if direction == "SELL" and ema50.iloc[-1] >= ema200.iloc[-1]:
                        return False
                    
                    # 2. ADX > 25 (Trend strength)
                    # Simple ADX calculation or from indicators service
                    from app.services.indicators import indicator_service
                    ind = indicator_service.calculate_all(df_5m)
                    if ind.get("ADX", 0) <= 25:
                        return False
                    
                    # 3. MACD aligned
                    macd = ind.get("MACD", 0)
                    signal_macd = ind.get("MACD_Signal", 0)
                    if direction == "BUY" and macd <= signal_macd:
                        return False
                    if direction == "SELL" and macd >= signal_macd:
                        return False
                    
                    # 4. ATR increasing (Volatilidad creciente)
                    atr = df_5m["high"] - df_5m["low"] # simplified
                    atr_sma = atr.rolling(window=14).mean()
                    if atr_sma.iloc[-1] <= atr_sma.iloc[-2]:
                        return False

            # General structural validation
            for tf in self.ANALYSIS_TIMEFRAMES:
                df = await market_data_service.get_time_series(asset, interval=tf, outputsize=100)
                if df is None or df.empty:
                    continue
                ema200 = df["close"].ewm(span=200, adjust=False).mean()
                if len(ema200) > 0:
                    if direction == "BUY" and df["close"].iloc[-1] < ema200.iloc[-1]:
                        return False
                    if direction == "SELL" and df["close"].iloc[-1] > ema200.iloc[-1]:
                        return False
            return True
        except:
            return True

    def _has_active_signal(self, asset: str) -> bool:
        for signal in self.active_signals.values():
            if signal.asset == asset and signal.status == SignalStatus.ACTIVE:
                return True
        return excel_manager.has_active_signal(asset)

    def get_active_signals(self) -> List[Signal]:
        """Get all active signals from memory."""
        return [s for s in self.active_signals.values() if s.status == SignalStatus.ACTIVE]


signal_engine = SignalEngine()
