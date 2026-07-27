"""
Motor de las 4 estrategias de trading multi-timeframe descritas en
"Guía Detallada: 4 Estrategias de Trading Multi-Timeframe" (documento
aportado por el usuario, 2026-07-23).

Cada estrategia se implementa como una cascada de 3 fases (Dirección ->
Confirmación -> Entrada), replicando las reglas exactas del documento
en cada fase. Si CUALQUIER fase no se cumple, la estrategia se
descarta para ese activo en ese momento (no se fuerza una señal
parcial).

Este módulo es independiente del motor de señales genérico existente
(`signal_engine.py` / `indicators.py`, con sus 18 indicadores de
confluencia) -- ambos pueden coexistir. Ver `strategy_selector.py`
para la lógica que decide, por activo y momento, cuál de las 4
estrategias aplica (o ninguna).
"""
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from loguru import logger
import pandas as pd

from app.services.market_data import market_data_service
from app.services.indicators import indicator_service
from app.models.asset import Asset
from app.core.config import settings
from app.services import strategy_indicators as si


@dataclass
class StrategyCandidate:
    """Resultado de una estrategia que superó sus 3 fases para un activo."""
    strategy: str
    asset: str
    direction: str  # "BUY" / "SELL"
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_reward_min: float
    risk_pct: float
    details: List[str] = field(default_factory=list)


class MultiTimeframeStrategyEngine:
    """Evalúa las 4 estrategias del documento para un activo dado."""

    # ------------------------------------------------------------------
    # Estrategia 1: Tendencia Multi-Timeframe (Trend Following)
    # Estilo: Swing | Horizonte: días a semanas | R:R min 1:2 | Riesgo 1%
    # ------------------------------------------------------------------
    async def evaluate_trend_mtf(self, asset: str) -> Optional[StrategyCandidate]:
        details = []
        try:
            df_daily = await market_data_service.get_time_series(asset, interval="1d", outputsize=120)
            if df_daily is None or len(df_daily) < 60:
                return None
            df_weekly = si.resample_to_weekly(df_daily)

            # --- Fase 1: Dirección (D1/W1) ---
            ema50_d1 = si.calc_ema_series(df_daily, 50).iloc[-1]
            ema200_d1 = si.calc_ema_series(df_daily, 200).iloc[-1] if len(df_daily) >= 200 else None
            if ema200_d1 is None or pd.isna(ema200_d1):
                # Con menos de 200 velas diarias disponibles, usamos una EMA200
                # calculada con los datos disponibles (igual se exige suficiente
                # historial arriba: >=60 velas) -- se documenta la limitación.
                ema200_d1 = si.calc_ema_series(df_daily, min(200, len(df_daily) - 1)).iloc[-1]

            current_price = df_daily["close"].iloc[-1]
            if ema50_d1 > ema200_d1:
                bias = "BUY"
            elif ema50_d1 < ema200_d1:
                bias = "SELL"
            else:
                return None
            details.append(f"Fase 1: EMA50={ema50_d1:.5f} {'>' if bias=='BUY' else '<'} EMA200={ema200_d1:.5f} -> sesgo {bias}")

            structure = si.price_structure_trend(df_daily, lookback=8, order=2)
            expected_structure = "bullish" if bias == "BUY" else "bearish"
            if structure != expected_structure:
                details.append(f"Fase 1: estructura de precio '{structure}' no confirma el sesgo {bias} -> descartada")
                return None
            details.append(f"Fase 1: estructura de precio '{structure}' confirma el sesgo")

            # Invalidación: precio cerró por debajo/encima de la EMA200
            if bias == "BUY" and current_price < ema200_d1:
                details.append("Fase 1: precio cerró por debajo de EMA200 en sesgo alcista -> invalidado")
                return None
            if bias == "SELL" and current_price > ema200_d1:
                details.append("Fase 1: precio cerró por encima de EMA200 en sesgo bajista -> invalidado")
                return None

            # --- Fase 2: Confirmación (H4) ---
            df_h4 = await market_data_service.get_time_series(asset, interval="4h", outputsize=200)
            if df_h4 is None or len(df_h4) < 30:
                return None

            fib_info = si.last_impulse_fibonacci(df_h4, lookback=60)
            if fib_info is None:
                details.append("Fase 2: no se pudo calcular el último impulso/Fibonacci -> descartada")
                return None

            ema20_h4 = si.calc_ema_series(df_h4, 20).iloc[-1]
            price_h4 = df_h4["close"].iloc[-1]
            levels = fib_info["levels"]
            in_fib_zone = min(levels["0.382"], levels["0.618"]) <= price_h4 <= max(levels["0.382"], levels["0.618"])
            near_ema20 = abs(price_h4 - ema20_h4) <= (si.calc_atr_series(df_h4, 14).iloc[-1] or 0) * 0.5
            if not (in_fib_zone or near_ema20):
                details.append("Fase 2: precio no está en zona de valor (EMA20 H4 / Fib 38.2-61.8%) -> descartada")
                return None
            details.append("Fase 2: precio en zona de valor (EMA20 H4 o retroceso Fibonacci)")

            # Descartar si el retroceso supera 78.6%
            beyond_786 = price_h4 < levels["0.786"] if bias == "BUY" else price_h4 > levels["0.786"]
            if beyond_786:
                details.append("Fase 2: retroceso supera el 78.6% de Fibonacci -> posible cambio de tendencia, descartada")
                return None

            rsi_h4_series = si.calc_rsi_series(df_h4, 14)
            rsi_now, rsi_prev = rsi_h4_series.iloc[-1], rsi_h4_series.iloc[-2]
            if bias == "BUY":
                rsi_confirmed = rsi_prev < 30 <= rsi_now  # cruce de vuelta desde sobreventa
            else:
                rsi_confirmed = rsi_prev > 70 >= rsi_now  # cruce de vuelta desde sobrecompra
            if not rsi_confirmed:
                details.append("Fase 2: RSI(14) H4 no confirma cruce de vuelta desde extremo -> descartada")
                return None
            details.append(f"Fase 2: RSI(14) H4 confirma cruce de vuelta ({rsi_prev:.1f} -> {rsi_now:.1f})")

            # --- Fase 3: Entrada (H1/M15) ---
            df_h1 = await market_data_service.get_time_series(asset, interval="1h", outputsize=100)
            if df_h1 is None or len(df_h1) < 20:
                return None

            recent_range = df_h1.iloc[-10:-1]
            minor_high, minor_low = recent_range["high"].max(), recent_range["low"].min()
            last_h1 = df_h1.iloc[-1]
            broke_structure = (last_h1["close"] > minor_high) if bias == "BUY" else (last_h1["close"] < minor_low)
            if not broke_structure:
                details.append("Fase 3: sin ruptura confirmada (cierre de vela) de la estructura menor H1 -> descartada")
                return None

            confirmation = si.is_bullish_engulfing(df_h1) if bias == "BUY" else si.is_bearish_engulfing(df_h1)
            pin = si.is_pin_bar(df_h1)
            pin_ok = (pin == "bullish" and bias == "BUY") or (pin == "bearish" and bias == "SELL")
            if not (confirmation or pin_ok):
                details.append("Fase 3: sin vela de confirmación (envolvente/pin bar) -> descartada")
                return None
            details.append("Fase 3: ruptura confirmada + vela de confirmación en zona de valor")

            entry_price = float(last_h1["close"])
            atr_h1 = si.calc_atr_series(df_h1, 14).iloc[-1]
            pip_info = Asset.get_pip_info(asset)
            pip_size = pip_info["pip_size"]
            sl_buffer = 1.0 * atr_h1
            candle_extreme = last_h1["low"] if bias == "BUY" else last_h1["high"]
            base_sl_distance = max(abs(entry_price - candle_extreme), 5 * pip_size)
            sl_distance = base_sl_distance + sl_buffer

            stop_loss = entry_price - sl_distance if bias == "BUY" else entry_price + sl_distance
            tp1 = minor_high if bias == "SELL" else minor_high  # nivel previo más cercano (estructura ya detectada)
            tp1 = minor_low if bias == "SELL" else minor_high
            # Asegurar relación mínima 1:1.5 en TP1
            min_tp1_distance = sl_distance * 1.5
            if abs(tp1 - entry_price) < min_tp1_distance:
                tp1 = entry_price + min_tp1_distance if bias == "BUY" else entry_price - min_tp1_distance

            tp2 = fib_info["levels"]["1.618_ext"] if bias == "BUY" else (
                fib_info["swing_low"] - (fib_info["swing_high"] - fib_info["swing_low"]) * 0.618
            )

            return StrategyCandidate(
                strategy="TREND_MTF", asset=asset, direction=bias,
                entry_price=entry_price, stop_loss=stop_loss,
                take_profit_1=tp1, take_profit_2=tp2,
                risk_reward_min=2.0, risk_pct=1.0, details=details
            )
        except Exception as e:
            logger.error(f"Error evaluando TREND_MTF para {asset}: {e}")
            return None

    # ------------------------------------------------------------------
    # Estrategia 2: Ruptura con Confirmación de Volumen (Breakout + Volume)
    # Estilo: Intradía | Horizonte: horas | R:R min 1:2 | Riesgo 0.5-1%
    # ------------------------------------------------------------------
    async def evaluate_breakout_volume(self, asset: str) -> Optional[StrategyCandidate]:
        details = []
        try:
            df_h4 = await market_data_service.get_time_series(asset, interval="4h", outputsize=100)
            if df_h4 is None or len(df_h4) < 30:
                return None

            # --- Fase 1: Identificación (H4/Diario) ---
            squeeze = si.detect_bollinger_squeeze(df_h4)
            atr_compressed = si.atr_below_average(df_h4)
            if not (squeeze["is_squeeze"] and atr_compressed):
                details.append("Fase 1: sin squeeze de volatilidad (Bollinger + ATR comprimido) -> descartada")
                return None
            details.append(f"Fase 1: squeeze detectado (percentil de banda {squeeze['percentile']:.0f}%, ATR comprimido)")

            range_info = si.detect_consolidation_range(df_h4, min_candles=5, lookback=20)
            if range_info is None:
                return None

            # --- Fase 2: Confirmación (H1) ---
            df_h1 = await market_data_service.get_time_series(asset, interval="1h", outputsize=100)
            if df_h1 is None or len(df_h1) < 25:
                return None

            last_h1 = df_h1.iloc[-1]
            broke_up = last_h1["close"] > range_info["high"]
            broke_down = last_h1["close"] < range_info["low"]
            if not (broke_up or broke_down):
                details.append("Fase 2: sin cierre de vela H1 fuera del rango marcado -> descartada")
                return None
            direction = "BUY" if broke_up else "SELL"

            rel_vol = si.relative_volume(df_h1, lookback=20)
            atr_h1_series = si.calc_atr_series(df_h1, 14)
            atr_ratio_proxy = atr_h1_series.iloc[-1] / atr_h1_series.iloc[-20:].mean() if atr_h1_series.iloc[-20:].mean() else 1.0
            volume_confirmed = rel_vol >= 1.5 or atr_ratio_proxy >= 1.5  # proxy de volumen por ATR en forex
            if not volume_confirmed:
                details.append(f"Fase 2: volumen/ATR de la ruptura insuficiente (rel_vol={rel_vol:.2f}) -> descartada")
                return None
            details.append(f"Fase 2: ruptura con volumen/ATR confirmado (rel_vol={rel_vol:.2f})")

            atr_h4 = si.calc_atr_series(df_h4, 14).iloc[-1]
            price_after = last_h1["close"]
            # Confirmar que no hay resistencia/soporte mayor a menos de 1xATR justo después
            recent_extremes = df_h4["high"].tail(30).max() if direction == "BUY" else df_h4["low"].tail(30).min()
            blocked = abs(recent_extremes - price_after) < atr_h4 and (
                (direction == "BUY" and recent_extremes > price_after) or
                (direction == "SELL" and recent_extremes < price_after)
            )
            if blocked:
                details.append("Fase 2: zona de S/R mayor a menos de 1xATR podría frenar el movimiento -> descartada")
                return None

            # --- Fase 3: Entrada (M15/M5) ---
            df_m15 = await market_data_service.get_time_series(asset, interval="15m", outputsize=60)
            if df_m15 is None or len(df_m15) < 10:
                return None

            level = range_info["high"] if direction == "BUY" else range_info["low"]
            last_m15 = df_m15.iloc[-1]
            near_retest = abs(last_m15["low" if direction == "BUY" else "high"] - level) <= (si.calc_atr_series(df_m15, 14).iloc[-1] or 0) * 1.5
            rejection = (
                last_m15["close"] > level and last_m15["low"] <= level
            ) if direction == "BUY" else (
                last_m15["close"] < level and last_m15["high"] >= level
            )
            if not (near_retest and rejection):
                details.append("Fase 3: sin retest + vela de rechazo del nivel roto -> descartada")
                return None
            details.append("Fase 3: retest confirmado con vela de rechazo")

            entry_price = float(last_m15["close"])
            atr_m15 = si.calc_atr_series(df_m15, 14).iloc[-1]
            retest_extreme = last_m15["low"] if direction == "BUY" else last_m15["high"]
            sl_distance = abs(entry_price - retest_extreme) + 0.5 * atr_m15
            stop_loss = entry_price - sl_distance if direction == "BUY" else entry_price + sl_distance

            range_height = range_info["high"] - range_info["low"]
            tp1 = entry_price + range_height if direction == "BUY" else entry_price - range_height
            structural_h1 = df_h1["high"].tail(30).max() if direction == "BUY" else df_h1["low"].tail(30).min()
            tp2 = structural_h1

            return StrategyCandidate(
                strategy="BREAKOUT_VOLUME", asset=asset, direction=direction,
                entry_price=entry_price, stop_loss=stop_loss,
                take_profit_1=tp1, take_profit_2=tp2,
                risk_reward_min=2.0, risk_pct=0.75, details=details
            )
        except Exception as e:
            logger.error(f"Error evaluando BREAKOUT_VOLUME para {asset}: {e}")
            return None

    # ------------------------------------------------------------------
    # Estrategia 3: Reversión en Zonas Clave (Price Action + Divergencia)
    # Estilo: Swing/Intradía | Horizonte: horas a días | R:R min 1:2.5 | Riesgo 1%
    # ------------------------------------------------------------------
    async def evaluate_reversal_zones(self, asset: str) -> Optional[StrategyCandidate]:
        details = []
        try:
            df_daily = await market_data_service.get_time_series(asset, interval="1d", outputsize=120)
            if df_daily is None or len(df_daily) < 40:
                return None

            # --- Fase 1: Zona (Semanal/Diario) ---
            swing_highs, swing_lows = si.detect_swing_points(df_daily, order=3)
            pip_info = Asset.get_pip_info(asset)
            tolerance = pip_info["pip_size"] * 20  # tolerancia para considerar "el mismo nivel"

            def count_touches(level, points):
                return sum(1 for _, p in points if abs(p - level) <= tolerance)

            candidate_zones = []
            for _, price in (swing_highs + swing_lows):
                touches = count_touches(price, swing_highs) + count_touches(price, swing_lows)
                if touches >= 2:
                    candidate_zones.append(price)
            if not candidate_zones:
                details.append("Fase 1: sin zonas de soporte/resistencia con 2+ toques -> descartada")
                return None

            current_price = df_daily["close"].iloc[-1]
            nearest_zone = min(candidate_zones, key=lambda z: abs(z - current_price))
            atr_d1 = si.calc_atr_series(df_daily, 14).iloc[-1]
            if abs(nearest_zone - current_price) > atr_d1 * 1.5:
                details.append("Fase 1: precio no está lo bastante cerca de una zona clave -> descartada")
                return None

            # Descartar zonas "quemadas" (rotas con cierre D1 en los últimos 10 periodos)
            recent_closes = df_daily["close"].tail(10)
            burned = any(
                (c > nearest_zone + tolerance) if current_price < nearest_zone else (c < nearest_zone - tolerance)
                for c in recent_closes
            )
            if burned:
                details.append("Fase 1: la zona fue rota recientemente (nivel 'quemado') -> descartada")
                return None
            details.append(f"Fase 1: zona clave identificada en {nearest_zone:.5f} con múltiples toques históricos")

            direction = "BUY" if current_price <= nearest_zone else "SELL"

            # --- Fase 2: Confirmación (H4) -- divergencia ---
            df_h4 = await market_data_service.get_time_series(asset, interval="4h", outputsize=150)
            if df_h4 is None or len(df_h4) < 40:
                return None

            rsi_h4 = si.calc_rsi_series(df_h4, 14)
            divergence = si.detect_regular_divergence(df_h4, rsi_h4, order=2, lookback=60)
            expected_div = "bullish" if direction == "BUY" else "bearish"
            if divergence != expected_div:
                macd_h4 = si.calc_macd_series(df_h4)["histogram"]
                divergence = si.detect_regular_divergence(df_h4, macd_h4, order=2, lookback=60)
            if divergence != expected_div:
                details.append("Fase 2: sin divergencia regular clara (RSI/MACD) en la zona -> descartada (no se opera solo por la zona)")
                return None
            details.append(f"Fase 2: divergencia {divergence} confirmada en RSI/MACD H4")

            # --- Fase 3: Entrada (H1/M30) ---
            df_h1 = await market_data_service.get_time_series(asset, interval="1h", outputsize=60)
            if df_h1 is None or len(df_h1) < 15:
                return None

            reversal_engulf = si.is_bullish_engulfing(df_h1) if direction == "BUY" else si.is_bearish_engulfing(df_h1)
            reversal_pin = si.is_pin_bar(df_h1)
            pin_ok = (reversal_pin == "bullish" and direction == "BUY") or (reversal_pin == "bearish" and direction == "SELL")
            if not (reversal_engulf or pin_ok):
                details.append("Fase 3: sin patrón de vela de reversión en H1 -> descartada")
                return None
            details.append("Fase 3: patrón de reversión confirmado en H1")

            last_h1 = df_h1.iloc[-1]
            entry_price = float(last_h1["close"])
            atr_h1 = si.calc_atr_series(df_h1, 14).iloc[-1]
            extreme = df_h1["low"].tail(20).min() if direction == "BUY" else df_h1["high"].tail(20).max()
            sl_distance = abs(entry_price - extreme) + 0.5 * atr_h1
            stop_loss = entry_price - sl_distance if direction == "BUY" else entry_price + sl_distance

            swing_h_local, swing_l_local = si.detect_swing_points(df_h1.tail(30), order=2)
            if direction == "BUY":
                tp1_candidates = [p for _, p in swing_h_local if p > entry_price]
                tp1 = min(tp1_candidates) if tp1_candidates else entry_price + sl_distance * 2.5
            else:
                tp1_candidates = [p for _, p in swing_l_local if p < entry_price]
                tp1 = max(tp1_candidates) if tp1_candidates else entry_price - sl_distance * 2.5

            other_zones = [z for z in candidate_zones if z != nearest_zone]
            tp2 = min(other_zones, key=lambda z: abs(z - entry_price)) if other_zones else (
                entry_price + sl_distance * 3.0 if direction == "BUY" else entry_price - sl_distance * 3.0
            )

            return StrategyCandidate(
                strategy="REVERSAL_ZONES", asset=asset, direction=direction,
                entry_price=entry_price, stop_loss=stop_loss,
                take_profit_1=tp1, take_profit_2=tp2,
                risk_reward_min=2.5, risk_pct=1.0, details=details
            )
        except Exception as e:
            logger.error(f"Error evaluando REVERSAL_ZONES para {asset}: {e}")
            return None

    # ------------------------------------------------------------------
    # Estrategia 4: Scalping con Triple Confirmación (Intradía rápido)
    # Estilo: Scalping | Horizonte: minutos | R:R min 1:2 | Riesgo 0.25-0.5%
    # ------------------------------------------------------------------
    async def evaluate_scalping_triple(self, asset: str) -> Optional[StrategyCandidate]:
        details = []
        try:
            df_h1 = await market_data_service.get_time_series(asset, interval="1h", outputsize=60)
            if df_h1 is None or len(df_h1) < 20:
                return None

            # --- Fase 1: Sesgo (H1) ---
            ema50_h1 = si.calc_ema_series(df_h1, 50).iloc[-1]
            current_price = df_h1["close"].iloc[-1]
            bias = "BUY" if current_price > ema50_h1 else "SELL"

            structure = si.price_structure_trend(df_h1, lookback=6, order=1)
            expected = "bullish" if bias == "BUY" else "bearish"
            if structure != expected:
                details.append("Fase 1: estructura H1 no confirma al menos 2 máximos/mínimos a favor del sesgo -> descartada")
                return None
            details.append(f"Fase 1: sesgo {bias} confirmado (precio vs EMA50 H1 + estructura)")

            # --- Fase 2: Confirmación (M15) ---
            df_m15 = await market_data_service.get_time_series(asset, interval="15m", outputsize=80)
            if df_m15 is None or len(df_m15) < 25:
                return None

            ema9 = si.calc_ema_series(df_m15, 9)
            ema21 = si.calc_ema_series(df_m15, 21)
            cross_now = ema9.iloc[-1] > ema21.iloc[-1] if bias == "BUY" else ema9.iloc[-1] < ema21.iloc[-1]
            cross_prev = ema9.iloc[-2] <= ema21.iloc[-2] if bias == "BUY" else ema9.iloc[-2] >= ema21.iloc[-2]
            recent_cross = cross_now and (cross_prev or (
                (ema9.iloc[-3] <= ema21.iloc[-3]) if bias == "BUY" else (ema9.iloc[-3] >= ema21.iloc[-3])
            ))
            if not recent_cross:
                details.append("Fase 2: sin cruce reciente de EMA9/EMA21 M15 a favor del sesgo -> descartada")
                return None

            rsi_m15 = si.calc_rsi_series(df_m15, 14)
            rsi_now, rsi_prev = rsi_m15.iloc[-1], rsi_m15.iloc[-2]
            in_range = 40 <= rsi_now <= 60
            turning_favor = (rsi_now > rsi_prev) if bias == "BUY" else (rsi_now < rsi_prev)
            if not (in_range and turning_favor):
                details.append("Fase 2: RSI(14) M15 fuera de 40-60 o no gira a favor del sesgo -> descartada")
                return None
            details.append(f"Fase 2: cruce EMA9/21 + RSI M15 ({rsi_now:.1f}) girando a favor del sesgo")

            # --- Fase 3: Entrada (M5/M1) ---
            df_m5 = await market_data_service.get_time_series(asset, interval="5m", outputsize=30)
            if df_m5 is None or len(df_m5) < 10:
                return None

            range_info = si.detect_consolidation_range(df_m5, min_candles=3, lookback=8)
            if range_info is None:
                return None

            last_m5 = df_m5.iloc[-1]
            micro_break = (last_m5["close"] > range_info["high"]) if bias == "BUY" else (last_m5["close"] < range_info["low"])
            impulse = si.is_impulse_candle(df_m5, body_ratio=0.6)
            impulse_ok = (impulse == "bullish" and bias == "BUY") or (impulse == "bearish" and bias == "SELL")
            if not (micro_break and impulse_ok):
                details.append("Fase 3: sin micro-ruptura + vela de impulso en M5 -> descartada")
                return None
            details.append("Fase 3: micro-ruptura confirmada con vela de impulso en M5")

            entry_price = float(last_m5["close"])
            atr_m5 = si.calc_atr_series(df_m5, 14).iloc[-1]
            last3_high = df_m5["high"].tail(3).max()
            last3_low = df_m5["low"].tail(3).min()
            raw_sl_distance = (entry_price - last3_low) if bias == "BUY" else (last3_high - entry_price)
            sl_distance = min(raw_sl_distance, atr_m5) if raw_sl_distance > 0 else atr_m5
            sl_distance = max(sl_distance, atr_m5 * 0.3)  # evitar un SL de 0

            stop_loss = entry_price - sl_distance if bias == "BUY" else entry_price + sl_distance
            tp_distance = sl_distance * 2.0  # 1:2 fijo mínimo
            tp1 = entry_price + tp_distance if bias == "BUY" else entry_price - tp_distance
            tp2 = tp1  # objetivo único 1:2 con cierre parcial en 1:1 (ver risk mgmt del documento)

            return StrategyCandidate(
                strategy="SCALPING_TRIPLE", asset=asset, direction=bias,
                entry_price=entry_price, stop_loss=stop_loss,
                take_profit_1=entry_price + sl_distance if bias == "BUY" else entry_price - sl_distance,  # cierre parcial en 1:1
                take_profit_2=tp2,
                risk_reward_min=2.0, risk_pct=0.375, details=details
            )
        except Exception as e:
            logger.error(f"Error evaluando SCALPING_TRIPLE para {asset}: {e}")
            return None

    # ------------------------------------------------------------------
    # Evaluación conjunta: intenta las 4 en orden de prioridad
    # ------------------------------------------------------------------
    async def evaluate_all(self, asset: str) -> List[StrategyCandidate]:
        """
        Evalúa las 4 estrategias para un activo y retorna todas las que
        superaron sus 3 fases (puede haber 0, 1, o varias coincidiendo).
        No se prioriza aquí cuál usar -- eso lo decide
        `strategy_selector.py` según el régimen de mercado detectado.
        """
        results = []
        for name, coro in [
            ("TREND_MTF", self.evaluate_trend_mtf(asset)),
            ("BREAKOUT_VOLUME", self.evaluate_breakout_volume(asset)),
            ("REVERSAL_ZONES", self.evaluate_reversal_zones(asset)),
            ("SCALPING_TRIPLE", self.evaluate_scalping_triple(asset)),
        ]:
            try:
                candidate = await coro
                if candidate:
                    results.append(candidate)
            except Exception as e:
                logger.error(f"Error evaluando {name} para {asset}: {e}")
        return results


strategy_engine = MultiTimeframeStrategyEngine()
