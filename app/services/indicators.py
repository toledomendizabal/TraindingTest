"""Technical indicators calculation service."""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from loguru import logger
from app.models.indicator import IndicatorConfig, get_default_indicators


class IndicatorService:
    """Service to calculate all 18 technical indicators."""

    def __init__(self, indicators: Optional[List[IndicatorConfig]] = None):
        self.indicators = indicators or get_default_indicators()

    def calculate_all(self, df: pd.DataFrame) -> Dict[str, any]:
        """Calculate all indicators on the dataframe."""
        results = {}

        if df is None or df.empty or len(df) < 200:
            logger.warning("Insufficient data for indicator calculation")
            return results

        try:
            # Trend Indicators
            results["EMA_200"] = self._calc_ema(df, 200)
            results["EMA_50"] = self._calc_ema(df, 50)
            results["EMA_20"] = self._calc_ema(df, 20)
            results["EMA_9"] = self._calc_ema(df, 9)
            results["PARABOLIC_SAR"] = self._calc_parabolic_sar(df)
            results["ICHIMOKU"] = self._calc_ichimoku(df)
            results["ADX_DMI"] = self._calc_adx(df)

            # Momentum Indicators
            results["RSI"] = self._calc_rsi(df)
            results["STOCHASTIC"] = self._calc_stochastic(df)
            results["MACD"] = self._calc_macd(df)
            results["CCI"] = self._calc_cci(df)
            results["AWESOME_OSCILLATOR"] = self._calc_ao(df)

            # Volatility Indicators
            results["BOLLINGER_BANDS"] = self._calc_bollinger(df)
            results["WILLIAMS_R"] = self._calc_williams_r(df)
            results["KELTNER_CHANNELS"] = self._calc_keltner(df)
            results["ATR"] = self._calc_atr(df)

            # Volume Indicators
            results["VOLUME_MA"] = self._calc_volume_ma(df)
            results["MFI"] = self._calc_mfi(df)

        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")

        return results

    def evaluate_signals(self, df: pd.DataFrame, indicators: Dict) -> Tuple[str, int, List[str]]:
        """
        Evaluate all indicators and determine BUY/SELL/NEUTRAL signal.
        Returns: (direction, indicators_met, details)
        """
        buy_signals = 0
        sell_signals = 0
        details = []
        current_price = df["close"].iloc[-1]

        # --- Market Phase Filter: Accumulation vs Distribution ---
        # Using ADX and Bollinger Bands to detect range (accumulation) vs trend (distribution)
        adx_data = indicators.get("ADX_DMI")
        bb_data = indicators.get("BOLLINGER_BANDS")
        
        is_distribution = False
        if adx_data and adx_data.get("adx", 0) > 20:
            is_distribution = True
            details.append(f"Market Phase: Distribution (ADX={adx_data['adx']:.1f})")
        elif bb_data:
            # Check if BB is expanding
            bb_width = (bb_data.get("upper", 0) - bb_data.get("lower", 0)) / bb_data.get("middle", 1)
            if bb_width > 0.002: # Threshold for expansion
                is_distribution = True
                details.append("Market Phase: Distribution (BB Expansion)")
        
        if not is_distribution:
            details.append("Market Phase: Accumulation (Signal Blocked)")
            return "NEUTRAL", 0, details


        # Layer 1: Trend Direction
        # EMA 200
        if "EMA_200" in indicators and indicators["EMA_200"] is not None:
            ema200 = indicators["EMA_200"]
            if current_price > ema200:
                buy_signals += 1
                details.append("EMA200: Price above (Bullish)")
            elif current_price < ema200:
                sell_signals += 1
                details.append("EMA200: Price below (Bearish)")

        # EMA 50
        if "EMA_50" in indicators and indicators["EMA_50"] is not None:
            ema50 = indicators["EMA_50"]
            ema200 = indicators.get("EMA_200")
            if ema200 and ema50 > ema200:
                buy_signals += 1
                details.append("EMA50 > EMA200 (Bullish)")
            elif ema200 and ema50 < ema200:
                sell_signals += 1
                details.append("EMA50 < EMA200 (Bearish)")

        # EMA Alignment
        if all(k in indicators for k in ["EMA_9", "EMA_20", "EMA_50"]):
            ema9 = indicators["EMA_9"]
            ema20 = indicators["EMA_20"]
            ema50 = indicators["EMA_50"]
            if ema9 and ema20 and ema50:
                if ema9 > ema20 > ema50:
                    buy_signals += 1
                    details.append("EMA Alignment: 9>20>50 (Bullish)")
                elif ema9 < ema20 < ema50:
                    sell_signals += 1
                    details.append("EMA Alignment: 9<20<50 (Bearish)")

        # Parabolic SAR
        if "PARABOLIC_SAR" in indicators and indicators["PARABOLIC_SAR"] is not None:
            sar = indicators["PARABOLIC_SAR"]
            if current_price > sar:
                buy_signals += 1
                details.append("SAR: Below price (Bullish)")
            else:
                sell_signals += 1
                details.append("SAR: Above price (Bearish)")

        # Ichimoku
        if "ICHIMOKU" in indicators and indicators["ICHIMOKU"] is not None:
            ichi = indicators["ICHIMOKU"]
            if ichi.get("signal") == "BUY":
                buy_signals += 1
                details.append("Ichimoku: Above cloud (Bullish)")
            elif ichi.get("signal") == "SELL":
                sell_signals += 1
                details.append("Ichimoku: Below cloud (Bearish)")

        # ADX/DMI
        if "ADX_DMI" in indicators and indicators["ADX_DMI"] is not None:
            adx_data = indicators["ADX_DMI"]
            if adx_data.get("adx", 0) > 25:
                if adx_data.get("plus_di", 0) > adx_data.get("minus_di", 0):
                    buy_signals += 1
                    details.append(f"ADX: {adx_data['adx']:.1f} +DI>{'-'}DI (Bullish)")
                else:
                    sell_signals += 1
                    details.append(f"ADX: {adx_data['adx']:.1f} -DI>+DI (Bearish)")

        # Layer 3: Momentum Triggers
        # RSI
        if "RSI" in indicators and indicators["RSI"] is not None:
            rsi = indicators["RSI"]
            if rsi < 30:
                buy_signals += 1
                details.append(f"RSI: {rsi:.1f} Oversold (Buy)")
            elif rsi > 70:
                sell_signals += 1
                details.append(f"RSI: {rsi:.1f} Overbought (Sell)")

        # Stochastic
        if "STOCHASTIC" in indicators and indicators["STOCHASTIC"] is not None:
            stoch = indicators["STOCHASTIC"]
            if stoch.get("k", 50) < 20 and stoch.get("d", 50) < 20:
                buy_signals += 1
                details.append("Stochastic: Oversold (Buy)")
            elif stoch.get("k", 50) > 80 and stoch.get("d", 50) > 80:
                sell_signals += 1
                details.append("Stochastic: Overbought (Sell)")

        # MACD
        if "MACD" in indicators and indicators["MACD"] is not None:
            macd_data = indicators["MACD"]
            if macd_data.get("histogram", 0) > 0 and macd_data.get("macd", 0) > macd_data.get("signal", 0):
                buy_signals += 1
                details.append("MACD: Bullish crossover")
            elif macd_data.get("histogram", 0) < 0 and macd_data.get("macd", 0) < macd_data.get("signal", 0):
                sell_signals += 1
                details.append("MACD: Bearish crossover")

        # CCI
        if "CCI" in indicators and indicators["CCI"] is not None:
            cci = indicators["CCI"]
            if cci < -100:
                buy_signals += 1
                details.append(f"CCI: {cci:.1f} Oversold (Buy)")
            elif cci > 100:
                sell_signals += 1
                details.append(f"CCI: {cci:.1f} Overbought (Sell)")

        # Awesome Oscillator
        if "AWESOME_OSCILLATOR" in indicators and indicators["AWESOME_OSCILLATOR"] is not None:
            ao = indicators["AWESOME_OSCILLATOR"]
            if ao.get("signal") == "BUY":
                buy_signals += 1
                details.append("AO: Saucer Buy signal")
            elif ao.get("signal") == "SELL":
                sell_signals += 1
                details.append("AO: Saucer Sell signal")

        # Layer 2: Volatility / Value Zones
        # Bollinger Bands
        if "BOLLINGER_BANDS" in indicators and indicators["BOLLINGER_BANDS"] is not None:
            bb = indicators["BOLLINGER_BANDS"]
            if current_price <= bb.get("lower", 0):
                buy_signals += 1
                details.append("BB: Price at lower band (Buy)")
            elif current_price >= bb.get("upper", float("inf")):
                sell_signals += 1
                details.append("BB: Price at upper band (Sell)")

        # Williams %R
        if "WILLIAMS_R" in indicators and indicators["WILLIAMS_R"] is not None:
            wr = indicators["WILLIAMS_R"]
            if wr < -80:
                buy_signals += 1
                details.append(f"Williams %R: {wr:.1f} Oversold (Buy)")
            elif wr > -20:
                sell_signals += 1
                details.append(f"Williams %R: {wr:.1f} Overbought (Sell)")

        # Keltner Channels
        if "KELTNER_CHANNELS" in indicators and indicators["KELTNER_CHANNELS"] is not None:
            kc = indicators["KELTNER_CHANNELS"]
            if current_price > kc.get("upper", float("inf")):
                buy_signals += 1
                details.append("Keltner: Breakout above (Buy)")
            elif current_price < kc.get("lower", 0):
                sell_signals += 1
                details.append("Keltner: Breakout below (Sell)")

        # Volume
        if "VOLUME_MA" in indicators and indicators["VOLUME_MA"] is not None:
            vol = indicators["VOLUME_MA"]
            if vol.get("above_average", False):
                if buy_signals > sell_signals:
                    buy_signals += 1
                    details.append("Volume: Above average (Confirms direction)")
                elif sell_signals > buy_signals:
                    sell_signals += 1
                    details.append("Volume: Above average (Confirms direction)")

        # MFI
        if "MFI" in indicators and indicators["MFI"] is not None:
            mfi = indicators["MFI"]
            if mfi < 20:
                buy_signals += 1
                details.append(f"MFI: {mfi:.1f} Oversold (Buy)")
            elif mfi > 80:
                sell_signals += 1
                details.append(f"MFI: {mfi:.1f} Overbought (Sell)")

        # Determine direction
        total_signals = buy_signals + sell_signals
        if buy_signals > sell_signals and buy_signals >= 6:
            return "BUY", buy_signals, details
        elif sell_signals > buy_signals and sell_signals >= 6:
            return "SELL", sell_signals, details
        else:
            return "NEUTRAL", max(buy_signals, sell_signals), details

    # --- Individual indicator calculations ---

    def _calc_ema(self, df: pd.DataFrame, period: int) -> Optional[float]:
        """Calculate EMA."""
        try:
            ema = df["close"].ewm(span=period, adjust=False).mean()
            return float(ema.iloc[-1])
        except Exception:
            return None

    def _calc_parabolic_sar(self, df: pd.DataFrame) -> Optional[float]:
        """Calculate Parabolic SAR."""
        try:
            high = df["high"].values
            low = df["low"].values
            close = df["close"].values

            af = 0.02
            max_af = 0.2
            length = len(df)

            sar = np.zeros(length)
            trend = np.ones(length)
            ep = np.zeros(length)

            sar[0] = low[0]
            ep[0] = high[0]

            for i in range(1, length):
                if trend[i - 1] == 1:
                    sar[i] = sar[i - 1] + af * (ep[i - 1] - sar[i - 1])
                    sar[i] = min(sar[i], low[i - 1])
                    if i > 1:
                        sar[i] = min(sar[i], low[i - 2])

                    if low[i] < sar[i]:
                        trend[i] = -1
                        sar[i] = ep[i - 1]
                        ep[i] = low[i]
                        af = 0.02
                    else:
                        trend[i] = 1
                        if high[i] > ep[i - 1]:
                            ep[i] = high[i]
                            af = min(af + 0.02, max_af)
                        else:
                            ep[i] = ep[i - 1]
                else:
                    sar[i] = sar[i - 1] + af * (ep[i - 1] - sar[i - 1])
                    sar[i] = max(sar[i], high[i - 1])
                    if i > 1:
                        sar[i] = max(sar[i], high[i - 2])

                    if high[i] > sar[i]:
                        trend[i] = 1
                        sar[i] = ep[i - 1]
                        ep[i] = high[i]
                        af = 0.02
                    else:
                        trend[i] = -1
                        if low[i] < ep[i - 1]:
                            ep[i] = low[i]
                            af = min(af + 0.02, max_af)
                        else:
                            ep[i] = ep[i - 1]

            return float(sar[-1])
        except Exception:
            return None

    def _calc_ichimoku(self, df: pd.DataFrame) -> Optional[Dict]:
        """Calculate Ichimoku Cloud."""
        try:
            high = df["high"]
            low = df["low"]
            close = df["close"]

            tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
            kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
            senkou_a = ((tenkan + kijun) / 2).shift(26)
            senkou_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)

            current_price = close.iloc[-1]
            cloud_top = max(senkou_a.iloc[-1] if pd.notna(senkou_a.iloc[-1]) else 0,
                          senkou_b.iloc[-1] if pd.notna(senkou_b.iloc[-1]) else 0)
            cloud_bottom = min(senkou_a.iloc[-1] if pd.notna(senkou_a.iloc[-1]) else 0,
                            senkou_b.iloc[-1] if pd.notna(senkou_b.iloc[-1]) else 0)

            signal = "NEUTRAL"
            if current_price > cloud_top and tenkan.iloc[-1] > kijun.iloc[-1]:
                signal = "BUY"
            elif current_price < cloud_bottom and tenkan.iloc[-1] < kijun.iloc[-1]:
                signal = "SELL"

            return {
                "tenkan": float(tenkan.iloc[-1]) if pd.notna(tenkan.iloc[-1]) else None,
                "kijun": float(kijun.iloc[-1]) if pd.notna(kijun.iloc[-1]) else None,
                "senkou_a": float(senkou_a.iloc[-1]) if pd.notna(senkou_a.iloc[-1]) else None,
                "senkou_b": float(senkou_b.iloc[-1]) if pd.notna(senkou_b.iloc[-1]) else None,
                "signal": signal
            }
        except Exception:
            return None

    def _calc_adx(self, df: pd.DataFrame, period: int = 14) -> Optional[Dict]:
        """Calculate ADX and DMI."""
        try:
            high = df["high"]
            low = df["low"]
            close = df["close"]

            plus_dm = high.diff()
            minus_dm = -low.diff()

            plus_dm[plus_dm < 0] = 0
            minus_dm[minus_dm < 0] = 0

            mask = plus_dm > minus_dm
            plus_dm[~mask] = 0
            minus_dm[mask] = 0

            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

            atr = tr.rolling(period).mean()
            plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
            minus_di = 100 * (minus_dm.rolling(period).mean() / atr)

            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
            adx = dx.rolling(period).mean()

            return {
                "adx": float(adx.iloc[-1]) if pd.notna(adx.iloc[-1]) else 0,
                "plus_di": float(plus_di.iloc[-1]) if pd.notna(plus_di.iloc[-1]) else 0,
                "minus_di": float(minus_di.iloc[-1]) if pd.notna(minus_di.iloc[-1]) else 0,
            }
        except Exception:
            return None

    def _calc_rsi(self, df: pd.DataFrame, period: int = 14) -> Optional[float]:
        """Calculate RSI."""
        try:
            delta = df["close"].diff()
            gain = delta.where(delta > 0, 0).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            return float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else None
        except Exception:
            return None

    def _calc_stochastic(self, df: pd.DataFrame) -> Optional[Dict]:
        """Calculate Stochastic Oscillator."""
        try:
            k_period = 14
            d_period = 3

            low_min = df["low"].rolling(k_period).min()
            high_max = df["high"].rolling(k_period).max()

            k = 100 * (df["close"] - low_min) / (high_max - low_min)
            d = k.rolling(d_period).mean()

            return {
                "k": float(k.iloc[-1]) if pd.notna(k.iloc[-1]) else 50,
                "d": float(d.iloc[-1]) if pd.notna(d.iloc[-1]) else 50,
            }
        except Exception:
            return None

    def _calc_macd(self, df: pd.DataFrame) -> Optional[Dict]:
        """Calculate MACD."""
        try:
            ema12 = df["close"].ewm(span=12, adjust=False).mean()
            ema26 = df["close"].ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            histogram = macd_line - signal_line

            return {
                "macd": float(macd_line.iloc[-1]),
                "signal": float(signal_line.iloc[-1]),
                "histogram": float(histogram.iloc[-1]),
            }
        except Exception:
            return None

    def _calc_cci(self, df: pd.DataFrame, period: int = 20) -> Optional[float]:
        """Calculate CCI."""
        try:
            tp = (df["high"] + df["low"] + df["close"]) / 3
            sma = tp.rolling(period).mean()
            mad = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean())
            cci = (tp - sma) / (0.015 * mad)
            return float(cci.iloc[-1]) if pd.notna(cci.iloc[-1]) else None
        except Exception:
            return None

    def _calc_ao(self, df: pd.DataFrame) -> Optional[Dict]:
        """Calculate Awesome Oscillator."""
        try:
            median = (df["high"] + df["low"]) / 2
            ao = median.rolling(5).mean() - median.rolling(34).mean()

            signal = "NEUTRAL"
            if len(ao) >= 3:
                if ao.iloc[-1] > 0 and ao.iloc[-2] < ao.iloc[-1] and ao.iloc[-3] > ao.iloc[-2]:
                    signal = "BUY"
                elif ao.iloc[-1] < 0 and ao.iloc[-2] > ao.iloc[-1] and ao.iloc[-3] < ao.iloc[-2]:
                    signal = "SELL"

            return {"value": float(ao.iloc[-1]) if pd.notna(ao.iloc[-1]) else 0, "signal": signal}
        except Exception:
            return None

    def _calc_bollinger(self, df: pd.DataFrame, period: int = 20, std_dev: float = 2) -> Optional[Dict]:
        """Calculate Bollinger Bands."""
        try:
            sma = df["close"].rolling(period).mean()
            std = df["close"].rolling(period).std()

            return {
                "upper": float(sma.iloc[-1] + std_dev * std.iloc[-1]),
                "middle": float(sma.iloc[-1]),
                "lower": float(sma.iloc[-1] - std_dev * std.iloc[-1]),
            }
        except Exception:
            return None

    def _calc_williams_r(self, df: pd.DataFrame, period: int = 14) -> Optional[float]:
        """Calculate Williams %R."""
        try:
            high_max = df["high"].rolling(period).max()
            low_min = df["low"].rolling(period).min()
            wr = -100 * (high_max - df["close"]) / (high_max - low_min)
            return float(wr.iloc[-1]) if pd.notna(wr.iloc[-1]) else None
        except Exception:
            return None

    def _calc_keltner(self, df: pd.DataFrame) -> Optional[Dict]:
        """Calculate Keltner Channels."""
        try:
            ema20 = df["close"].ewm(span=20, adjust=False).mean()
            atr = self._calc_atr_series(df, 14)

            return {
                "upper": float(ema20.iloc[-1] + 2 * atr.iloc[-1]),
                "middle": float(ema20.iloc[-1]),
                "lower": float(ema20.iloc[-1] - 2 * atr.iloc[-1]),
            }
        except Exception:
            return None

    def _calc_atr(self, df: pd.DataFrame, period: int = 14) -> Optional[float]:
        """Calculate ATR."""
        try:
            atr_series = self._calc_atr_series(df, period)
            return float(atr_series.iloc[-1]) if pd.notna(atr_series.iloc[-1]) else None
        except Exception:
            return None

    def _calc_atr_series(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate ATR as a series."""
        tr1 = df["high"] - df["low"]
        tr2 = abs(df["high"] - df["close"].shift(1))
        tr3 = abs(df["low"] - df["close"].shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    def _calc_volume_ma(self, df: pd.DataFrame, period: int = 20) -> Optional[Dict]:
        """Calculate Volume Moving Average."""
        try:
            if "volume" not in df.columns or df["volume"].sum() == 0:
                return {"above_average": False, "ratio": 1.0}

            vol_ma = df["volume"].rolling(period).mean()
            current_vol = df["volume"].iloc[-1]
            ratio = current_vol / vol_ma.iloc[-1] if vol_ma.iloc[-1] > 0 else 1.0

            return {
                "above_average": ratio > 1.2,
                "ratio": float(ratio),
            }
        except Exception:
            return None

    def _calc_mfi(self, df: pd.DataFrame, period: int = 14) -> Optional[float]:
        """Calculate Money Flow Index."""
        try:
            if "volume" not in df.columns or df["volume"].sum() == 0:
                return 50.0  # Neutral if no volume data

            tp = (df["high"] + df["low"] + df["close"]) / 3
            mf = tp * df["volume"]

            positive_mf = mf.where(tp > tp.shift(1), 0).rolling(period).sum()
            negative_mf = mf.where(tp < tp.shift(1), 0).rolling(period).sum()

            mfi = 100 - (100 / (1 + positive_mf / negative_mf.replace(0, 1)))
            return float(mfi.iloc[-1]) if pd.notna(mfi.iloc[-1]) else 50.0
        except Exception:
            return 50.0


# Singleton instance
indicator_service = IndicatorService()
