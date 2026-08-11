"""
Motor de señales basado en ESTRATEGIAS (reemplaza el voto por indicadores).

======================================================================
QUÉ CAMBIA Y QUÉ NO CAMBIA
======================================================================
- CAMBIA: la forma en que se decide SI hay señal y en qué DIRECCIÓN.
  Antes: `indicator_service.evaluate_signals()` contaba cuántos de 18
  indicadores técnicos (RSI, MACD, EMAs, Bollinger, etc.) votaban BUY/SELL
  y exigía un mínimo (`min_indicators`).
  Ahora: cada activo tiene asignadas hasta 2 "estrategias óptimas" (según
  `Tablas_de_aplicacion.html`, tomadas del manual `Estrategias.html` -- 18
  estrategias de Scalping Institucional / Smart Money Concepts). El motor
  evalúa SOLO esas estrategias para ese activo y dispara señal cuando una
  de ellas se confirma con claridad.

- NO CAMBIA: todo lo que pasa DESPUÉS de tener (direction, confidence):
  el filtro de spread, el filtro de sesión, el filtro de volatilidad, la
  validación estructural multi-timeframe, el filtro de tendencia macro,
  el registro en Excel, el envío a MT5 y el monitoreo/backtesting de
  posiciones abiertas. Todo eso sigue viviendo en `signal_engine.py` y
  `position_monitor.py` exactamente como antes.

======================================================================
MAPEO ACTIVO -> ESTRATEGIAS (editable abajo en ASSET_GROUPS)
======================================================================
El mapeo activo-estrategia es una interpretación de la columna
"Estrategias Óptimas (Hasta 2)" de la tabla adjunta, cruzada contra los
títulos exactos de las 18 estrategias del manual. Es una propuesta de
partida, NO una verdad absoluta -- edítala libremente cambiando los
números de estrategia en `ASSET_GROUPS` si tu criterio difiere.

  1  Silver Bullet (Toma de Liquidez + CHoCH)
  2  Mitigación de Order Block en Sesión
  3  Trampa del Rango Asiático (Modelo AMD)
  4  Ruptura de Rango (Breakout Institucional con Volumen)
  5  Retroceso a EMA (Pullback Dinámico en Tendencia)
  6  Cruce de EMAs (Crossover de Momento en Cambio de Fase)
  7  Estocástico en Extremos (Agotamiento y Falsas Rupturas)
  8  Bandas de Bollinger (Rebote en Desviación Estándar y Squeeze)
  9  Reacción al VWAP (El Imán Institucional)
  10 Pin Bar en Soporte/Resistencia (Rechazo de Liquidez)
  11 Vela Envolvente (Engulfing de Absorción Algorítmica)
  12 Divergencia de RSI (Agotamiento de Impulso Institucional)
  13 Órdenes Limitadas en Niveles Clave (Sniper Entries en OB/FVG)
  14 Retroceso de Fibonacci (Entrada Áurea 0.618 / OTE 0.705-0.79)
  15 MACD Cruce de Señal y Momento 0 (Aceleración de Volatilidad)
  16 Volumen con Acumulación (Spike & Climax de Volumen)
  17 VSA (Volume Spread Analysis - No Demand / No Supply)
  18 Soporte/Resistencia Dinámica (Línea de Tendencia con Liquidez)

Solo 9 de las 18 quedaron asignadas por defecto (2 por cada uno de los 5
grupos de activos de la tabla). Las 9 restantes están implementadas como
funciones `_strategy_XX` y puedes asignarlas a cualquier grupo cambiando
la lista de números en `ASSET_GROUPS`.
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from loguru import logger

from app.services.indicators import indicator_service


# ======================================================================
# 1. MAPEO DE ACTIVOS -> GRUPO -> ESTRATEGIAS ÓPTIMAS + COMPLEMENTOS
# ======================================================================
# NOTA sobre el conteo "24": la tarjeta de resumen del dashboard adjunto
# dice "24 Divisas, Índices y Metales", pero la tabla adjunta en realidad
# lista 19 pares de divisas + 5 índices + 4 metales/materias primas = 28
# activos distintos. Se tomó el listado EXPLÍCITO de la tabla (28 activos)
# como fuente de verdad, ya que es más específico que el número suelto de
# la tarjeta. Si en realidad querías solo 24, dime cuáles 4 quitar.
ASSET_GROUPS: Dict[str, Dict] = {
    "FOREX_MAJORS": {
        "assets": ["EURUSD", "GBPUSD", "USDCHF", "NZDUSD"],
        "strategies": [1, 4],  # Silver Bullet (liquidez+CHoCH) / Breakout institucional
        "complementary": ["DXY", "US10Y"],
    },
    "FOREX_YEN_COMMODITY": {
        "assets": ["USDJPY", "AUDUSD", "USDCAD"],
        "strategies": [5, 6],  # Pullback EMA en tendencia / Cruce de EMAs (carry, news-based)
        "complementary": ["JP225", "WTI", "BRENT"],
    },
    "FOREX_CROSSES": {
        "assets": [
            "EURGBP", "EURJPY", "EURCHF", "GBPJPY", "CHFJPY", "AUDJPY",
            "CADJPY", "NZDJPY", "AUDNZD", "AUDCHF", "GBPCHF", "CADCHF",
        ],
        "strategies": [3, 18],  # Trampa rango asiático (AMD) / S-R dinámica con tendencia
        "complementary": ["GER40Cash", "STOXX50Cash", "EURUSD"],
    },
    "INDICES": {
        "assets": ["US30Cash", "US500Cash", "US100Cash", "GER40Cash", "STOXX50Cash"],
        "strategies": [16, 3],  # Volumen con acumulación (momentum) / AMD en apertura de sesión
        "complementary": ["VIX", "XAUUSD", "BUND"],
    },
    "METALS_COMMODITIES": {
        "assets": ["XAUUSD", "WTI", "BRENT", "COPPER"],
        "strategies": [8, 5],  # Bollinger (reversión/cobertura) / Pullback EMA (tendencia macro)
        "complementary": ["DXY", "TIPS", "AUDUSD"],
    },
}

# Traducción de los nombres genéricos de la tabla (por si se muestran en UI/reportes)
STRATEGY_NAMES = {
    1: "Silver Bullet (Toma de Liquidez + CHoCH)",
    2: "Mitigación de Order Block en Sesión",
    3: "Trampa del Rango Asiático (Modelo AMD)",
    4: "Ruptura de Rango (Breakout Institucional)",
    5: "Retroceso a EMA (Pullback en Tendencia)",
    6: "Cruce de EMAs (Crossover de Momento)",
    7: "Estocástico en Extremos",
    8: "Bandas de Bollinger (Rebote / Squeeze)",
    9: "Reacción al VWAP",
    10: "Pin Bar en Soporte/Resistencia",
    11: "Vela Envolvente (Engulfing)",
    12: "Divergencia de RSI",
    13: "Órdenes Limitadas en OB/FVG (Sniper Entry)",
    14: "Retroceso de Fibonacci (OTE 0.618-0.79)",
    15: "MACD Cruce de Señal / Cruce de Cero",
    16: "Volumen con Acumulación (Spike & Climax)",
    17: "VSA (No Demand / No Supply)",
    18: "Soporte/Resistencia Dinámica (Línea de Tendencia)",
}


def get_asset_group(asset: str) -> Optional[str]:
    asset_u = asset.upper().replace(".", "").replace("CASH", "Cash").replace("cash", "Cash")
    for group, info in ASSET_GROUPS.items():
        for a in info["assets"]:
            if a.upper() == asset.upper():
                return group
    return None


def get_strategies_for_asset(asset: str) -> List[int]:
    group = get_asset_group(asset)
    if group is None:
        # Activo no mapeado explícitamente: usa un set neutro razonable
        # (reversión + breakout) en lugar de bloquear el análisis.
        logger.warning(f"[strategy_engine] Activo '{asset}' sin grupo asignado en ASSET_GROUPS; usando estrategias por defecto [1, 4].")
        return [1, 4]
    return ASSET_GROUPS[group]["strategies"]


def get_complementary_assets(asset: str) -> List[str]:
    group = get_asset_group(asset)
    if group is None:
        return []
    return ASSET_GROUPS[group]["complementary"]


# ======================================================================
# 2. BLOQUES CONSTRUCTIVOS SMC (reutilizan / extienden indicator_service)
# ======================================================================
def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _detect_choch(df: pd.DataFrame, lookback: int = 20) -> Optional[str]:
    """
    Change of Character simplificado: compara el último swing high/low
    roto por CUERPO de vela (no mecha) contra la estructura previa.
    Retorna "BULLISH", "BEARISH" o None.
    """
    if len(df) < lookback + 5:
        return None
    recent = df.iloc[-lookback:]
    highs = recent["high"].values
    lows = recent["low"].values
    closes = recent["close"].values
    opens = recent["open"].values

    # Último máximo/mínimo "estructural" antes de las últimas 3 velas
    prior_high = highs[:-3].max()
    prior_low = lows[:-3].min()
    last_close = closes[-1]
    last_open = opens[-1]

    # CHoCH alcista: el cuerpo de una vela cierra por encima del último
    # máximo relevante tras una fase bajista (mínimos decrecientes previos).
    was_bearish_structure = lows[-6:-3].min() < lows[:-6].min() if len(lows) > 9 else False
    if last_close > prior_high and last_close > last_open:
        return "BULLISH"
    # CHoCH bajista: cierre de cuerpo por debajo del último mínimo relevante.
    if last_close < prior_low and last_close < last_open:
        return "BEARISH"
    return None


def _detect_order_blocks(df: pd.DataFrame, lookback: int = 30) -> List[Dict]:
    """
    Order Block simplificado: última vela contraria antes de un impulso
    fuerte (cuerpo > 1.5x el promedio de cuerpos recientes) que rompe
    estructura.
    """
    if len(df) < lookback:
        return []
    window = df.iloc[-lookback:].reset_index(drop=True)
    bodies = (window["close"] - window["open"]).abs()
    avg_body = bodies.mean()
    obs = []
    for i in range(1, len(window) - 1):
        impulse_body = bodies.iloc[i]
        if impulse_body > 1.5 * avg_body and avg_body > 0:
            impulsive_bullish = window["close"].iloc[i] > window["open"].iloc[i]
            candidate = window.iloc[i - 1]
            candidate_bearish = candidate["close"] < candidate["open"]
            if impulsive_bullish and candidate_bearish:
                obs.append({
                    "type": "BULLISH_OB",
                    "top": float(candidate["high"]),
                    "bottom": float(candidate["low"]),
                })
            elif (not impulsive_bullish) and (not candidate_bearish):
                obs.append({
                    "type": "BEARISH_OB",
                    "top": float(candidate["high"]),
                    "bottom": float(candidate["low"]),
                })
    return obs[-5:]


def _detect_inducement(df: pd.DataFrame, lookback: int = 15) -> bool:
    """Barrido reciente de un pequeño máximo/mínimo intermedio (trampa temprana)."""
    if len(df) < lookback:
        return False
    window = df.iloc[-lookback:]
    highs = window["high"].values
    lows = window["low"].values
    last_high, last_low = highs[-1], lows[-1]
    minor_high = highs[:-1].max()
    minor_low = lows[:-1].min()
    return bool(last_high > minor_high or last_low < minor_low)


def _asian_range(df: pd.DataFrame) -> Optional[Tuple[float, float]]:
    """
    Rango asiático aproximado sobre velas de 5m: usa las últimas ~34 velas
    (equivalente a ~2.8h) como proxy de la sesión Tokio/rango bajo. Ajustar
    si el timeframe de señal cambia.
    """
    if len(df) < 40:
        return None
    session = df.iloc[-40:-10]
    return float(session["low"].min()), float(session["high"].max())


def _bollinger(df: pd.DataFrame, period: int = 20, std_mult: float = 2.0):
    mid = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std()
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    return upper, mid, lower


def _vwap(df: pd.DataFrame) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"] if "volume" in df.columns else pd.Series(1.0, index=df.index)
    cum_vol = vol.cumsum().replace(0, np.nan)
    return (typical * vol).cumsum() / cum_vol


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


# ======================================================================
# 3. LAS 18 ESTRATEGIAS (cada una retorna None o dict con direction/detail)
# ======================================================================
def _strategy_1_silver_bullet(df: pd.DataFrame) -> Optional[Dict]:
    """Toma de liquidez (sweep) + CHoCH inmediato en la misma zona."""
    liquidity = indicator_service.detect_liquidity(df)
    choch = _detect_choch(df)
    last_close = float(df["close"].iloc[-1])
    if choch == "BULLISH" and liquidity["SSL"] and min(liquidity["SSL"][-3:]) < df["low"].iloc[-6:].min():
        return {"direction": "BUY", "detail": "Barrido de SSL + CHoCH alcista"}
    if choch == "BEARISH" and liquidity["BSL"] and max(liquidity["BSL"][-3:]) > df["high"].iloc[-6:].max():
        return {"direction": "SELL", "detail": "Barrido de BSL + CHoCH bajista"}
    return None


def _strategy_2_ob_mitigation(df: pd.DataFrame) -> Optional[Dict]:
    """Mitigación de Order Block: precio regresa a un OB reciente y reacciona."""
    obs = _detect_order_blocks(df)
    last_close = float(df["close"].iloc[-1])
    for ob in reversed(obs):
        if ob["bottom"] <= last_close <= ob["top"]:
            if ob["type"] == "BULLISH_OB":
                return {"direction": "BUY", "detail": "Mitigación de Order Block alcista"}
            else:
                return {"direction": "SELL", "detail": "Mitigación de Order Block bajista"}
    return None


def _strategy_3_amd_asian_range(df: pd.DataFrame) -> Optional[Dict]:
    """Trampa de rango asiático: falso quiebre del rango + reingreso."""
    rng = _asian_range(df)
    if rng is None:
        return None
    low, high = rng
    last = df.iloc[-3:]
    swept_high = last["high"].max() > high and last["close"].iloc[-1] < high
    swept_low = last["low"].min() < low and last["close"].iloc[-1] > low
    if swept_high:
        return {"direction": "SELL", "detail": "Falso quiebre alcista del rango asiático (AMD)"}
    if swept_low:
        return {"direction": "BUY", "detail": "Falso quiebre bajista del rango asiático (AMD)"}
    return None


def _strategy_4_breakout(df: pd.DataFrame) -> Optional[Dict]:
    """Ruptura de rango con expansión de rango real (proxy de volumen institucional)."""
    if len(df) < 30:
        return None
    recent_range = df["high"].iloc[-20:-1].max() - df["low"].iloc[-20:-1].min()
    last_candle_range = df["high"].iloc[-1] - df["low"].iloc[-1]
    breakout_up = df["close"].iloc[-1] > df["high"].iloc[-20:-1].max()
    breakout_down = df["close"].iloc[-1] < df["low"].iloc[-20:-1].min()
    strong_range = last_candle_range > 1.3 * (recent_range / 20 if recent_range else 0)
    if breakout_up and strong_range:
        return {"direction": "BUY", "detail": "Ruptura alcista de rango con expansión"}
    if breakout_down and strong_range:
        return {"direction": "SELL", "detail": "Ruptura bajista de rango con expansión"}
    return None


def _strategy_5_ema_pullback(df: pd.DataFrame) -> Optional[Dict]:
    """Pullback a EMA20/50 dentro de una tendencia definida por EMA200."""
    if len(df) < 210:
        return None
    ema20 = _ema(df["close"], 20)
    ema50 = _ema(df["close"], 50)
    ema200 = _ema(df["close"], 200)
    price = float(df["close"].iloc[-1])
    trend_up = ema50.iloc[-1] > ema200.iloc[-1]
    trend_down = ema50.iloc[-1] < ema200.iloc[-1]
    near_ema = abs(price - ema20.iloc[-1]) / price < 0.0015
    if trend_up and near_ema and price > ema200.iloc[-1]:
        return {"direction": "BUY", "detail": "Pullback a EMA20 en tendencia alcista (EMA50>EMA200)"}
    if trend_down and near_ema and price < ema200.iloc[-1]:
        return {"direction": "SELL", "detail": "Pullback a EMA20 en tendencia bajista (EMA50<EMA200)"}
    return None


def _strategy_6_ema_crossover(df: pd.DataFrame) -> Optional[Dict]:
    """Cruce reciente de EMA rápida sobre lenta (cambio de fase de momento)."""
    if len(df) < 55:
        return None
    fast = _ema(df["close"], 9)
    slow = _ema(df["close"], 21)
    cross_up = fast.iloc[-2] <= slow.iloc[-2] and fast.iloc[-1] > slow.iloc[-1]
    cross_down = fast.iloc[-2] >= slow.iloc[-2] and fast.iloc[-1] < slow.iloc[-1]
    if cross_up:
        return {"direction": "BUY", "detail": "Cruce alcista EMA9/EMA21"}
    if cross_down:
        return {"direction": "SELL", "detail": "Cruce bajista EMA9/EMA21"}
    return None


def _strategy_7_stochastic_extreme(df: pd.DataFrame) -> Optional[Dict]:
    if len(df) < 20:
        return None
    low_min = df["low"].rolling(14).min()
    high_max = df["high"].rolling(14).max()
    k = 100 * (df["close"] - low_min) / (high_max - low_min).replace(0, np.nan)
    k_now, k_prev = k.iloc[-1], k.iloc[-2]
    if k_prev < 20 and k_now >= 20:
        return {"direction": "BUY", "detail": "Estocástico saliendo de sobreventa (<20)"}
    if k_prev > 80 and k_now <= 80:
        return {"direction": "SELL", "detail": "Estocástico saliendo de sobrecompra (>80)"}
    return None


def _strategy_8_bollinger(df: pd.DataFrame) -> Optional[Dict]:
    upper, mid, lower = _bollinger(df)
    if pd.isna(upper.iloc[-1]) or pd.isna(lower.iloc[-1]):
        return None
    price = float(df["close"].iloc[-1])
    if price <= lower.iloc[-1]:
        return {"direction": "BUY", "detail": "Rebote en banda inferior de Bollinger"}
    if price >= upper.iloc[-1]:
        return {"direction": "SELL", "detail": "Rebote en banda superior de Bollinger"}
    return None


def _strategy_9_vwap_reaction(df: pd.DataFrame) -> Optional[Dict]:
    vwap = _vwap(df)
    if pd.isna(vwap.iloc[-1]):
        return None
    price = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2])
    vwap_now = float(vwap.iloc[-1])
    crossed_up = prev < vwap.iloc[-2] and price > vwap_now
    crossed_down = prev > vwap.iloc[-2] and price < vwap_now
    if crossed_up:
        return {"direction": "BUY", "detail": "Reacción alcista al cruzar VWAP"}
    if crossed_down:
        return {"direction": "SELL", "detail": "Reacción bajista al cruzar VWAP"}
    return None


def _strategy_10_pin_bar(df: pd.DataFrame) -> Optional[Dict]:
    last = df.iloc[-1]
    body = abs(last["close"] - last["open"])
    upper_wick = last["high"] - max(last["close"], last["open"])
    lower_wick = min(last["close"], last["open"]) - last["low"]
    if body == 0:
        return None
    if lower_wick > 2 * body and upper_wick < body:
        return {"direction": "BUY", "detail": "Pin bar de rechazo alcista"}
    if upper_wick > 2 * body and lower_wick < body:
        return {"direction": "SELL", "detail": "Pin bar de rechazo bajista"}
    return None


def _strategy_11_engulfing(df: pd.DataFrame) -> Optional[Dict]:
    if len(df) < 2:
        return None
    prev, last = df.iloc[-2], df.iloc[-1]
    bullish_engulf = (last["close"] > last["open"] and prev["close"] < prev["open"]
                      and last["close"] > prev["open"] and last["open"] < prev["close"])
    bearish_engulf = (last["close"] < last["open"] and prev["close"] > prev["open"]
                      and last["close"] < prev["open"] and last["open"] > prev["close"])
    if bullish_engulf:
        return {"direction": "BUY", "detail": "Vela envolvente alcista"}
    if bearish_engulf:
        return {"direction": "SELL", "detail": "Vela envolvente bajista"}
    return None


def _strategy_12_rsi_divergence(df: pd.DataFrame) -> Optional[Dict]:
    if len(df) < 30:
        return None
    rsi = _rsi(df["close"])
    price_low_idx = df["low"].iloc[-15:].idxmin()
    price_high_idx = df["high"].iloc[-15:].idxmax()
    try:
        prior_low = df["low"].iloc[-30:-15].min()
        prior_high = df["high"].iloc[-30:-15].max()
        prior_rsi_low = rsi.iloc[-30:-15].min()
        prior_rsi_high = rsi.iloc[-30:-15].max()
        curr_low = df["low"].iloc[-15:].min()
        curr_high = df["high"].iloc[-15:].max()
        curr_rsi_low = rsi.iloc[-15:].min()
        curr_rsi_high = rsi.iloc[-15:].max()
        if curr_low < prior_low and curr_rsi_low > prior_rsi_low:
            return {"direction": "BUY", "detail": "Divergencia alcista de RSI"}
        if curr_high > prior_high and curr_rsi_high < prior_rsi_high:
            return {"direction": "SELL", "detail": "Divergencia bajista de RSI"}
    except Exception:
        return None
    return None


def _strategy_13_sniper_ob_fvg(df: pd.DataFrame) -> Optional[Dict]:
    fvgs = indicator_service.detect_fvg(df)
    price = float(df["close"].iloc[-1])
    for fvg in reversed(fvgs[-5:]):
        if fvg["bottom"] <= price <= fvg["top"]:
            if fvg["type"] == "BULLISH":
                return {"direction": "BUY", "detail": "Entrada límite dentro de FVG alcista"}
            else:
                return {"direction": "SELL", "detail": "Entrada límite dentro de FVG bajista"}
    return None


def _strategy_14_fibonacci_ote(df: pd.DataFrame) -> Optional[Dict]:
    if len(df) < 30:
        return None
    swing = df.iloc[-30:]
    swing_high = swing["high"].max()
    swing_low = swing["low"].min()
    price = float(df["close"].iloc[-1])
    rng = swing_high - swing_low
    if rng <= 0:
        return None
    retr = (swing_high - price) / rng
    if 0.618 <= retr <= 0.79 and price > swing_low:
        return {"direction": "BUY", "detail": "Retroceso en zona OTE (0.618-0.79) desde mínimo"}
    retr_down = (price - swing_low) / rng
    if 0.618 <= retr_down <= 0.79 and price < swing_high:
        return {"direction": "SELL", "detail": "Retroceso en zona OTE (0.618-0.79) desde máximo"}
    return None


def _strategy_15_macd_cross(df: pd.DataFrame) -> Optional[Dict]:
    if len(df) < 40:
        return None
    ema12 = _ema(df["close"], 12)
    ema26 = _ema(df["close"], 26)
    macd = ema12 - ema26
    signal_line = _ema(macd, 9)
    cross_up = macd.iloc[-2] <= signal_line.iloc[-2] and macd.iloc[-1] > signal_line.iloc[-1]
    cross_down = macd.iloc[-2] >= signal_line.iloc[-2] and macd.iloc[-1] < signal_line.iloc[-1]
    if cross_up:
        return {"direction": "BUY", "detail": "Cruce alcista MACD/señal"}
    if cross_down:
        return {"direction": "SELL", "detail": "Cruce bajista MACD/señal"}
    return None


def _strategy_16_volume_spike(df: pd.DataFrame) -> Optional[Dict]:
    if "volume" not in df.columns or len(df) < 25:
        return None
    avg_vol = df["volume"].iloc[-21:-1].mean()
    last_vol = df["volume"].iloc[-1]
    if avg_vol <= 0:
        return None
    spike = last_vol > 2.0 * avg_vol
    if not spike:
        return None
    last = df.iloc[-1]
    if last["close"] > last["open"]:
        return {"direction": "BUY", "detail": "Spike de volumen con vela alcista (acumulación)"}
    else:
        return {"direction": "SELL", "detail": "Spike de volumen con vela bajista (distribución)"}


def _strategy_17_vsa(df: pd.DataFrame) -> Optional[Dict]:
    if "volume" not in df.columns or len(df) < 10:
        return None
    avg_vol = df["volume"].iloc[-11:-1].mean()
    last = df.iloc[-1]
    last_range = last["high"] - last["low"]
    avg_range = (df["high"] - df["low"]).iloc[-11:-1].mean()
    if avg_vol <= 0 or avg_range <= 0:
        return None
    low_vol = last["volume"] < 0.6 * avg_vol
    narrow_range = last_range < 0.7 * avg_range
    if low_vol and narrow_range:
        # "No Demand" / "No Supply": rango y volumen bajos tras un
        # movimiento -> posible agotamiento en la dirección contraria a la
        # vela previa.
        prev = df.iloc[-2]
        if prev["close"] < prev["open"]:
            return {"direction": "BUY", "detail": "No Supply tras vela bajista (VSA)"}
        else:
            return {"direction": "SELL", "detail": "No Demand tras vela alcista (VSA)"}
    return None


def _strategy_18_dynamic_sr(df: pd.DataFrame) -> Optional[Dict]:
    if len(df) < 40:
        return None
    # Línea de tendencia dinámica simplificada vía regresión lineal sobre
    # los máximos/mínimos recientes.
    window = df.iloc[-40:]
    x = np.arange(len(window))
    try:
        slope_low, intercept_low = np.polyfit(x, window["low"].values, 1)
        slope_high, intercept_high = np.polyfit(x, window["high"].values, 1)
    except Exception:
        return None
    price = float(df["close"].iloc[-1])
    trend_low_now = slope_low * (len(window) - 1) + intercept_low
    trend_high_now = slope_high * (len(window) - 1) + intercept_high
    liquidity = indicator_service.detect_liquidity(df)
    if slope_low > 0 and abs(price - trend_low_now) / price < 0.0015 and liquidity["SSL"]:
        return {"direction": "BUY", "detail": "Rebote en línea de tendencia alcista con liquidez"}
    if slope_high < 0 and abs(price - trend_high_now) / price < 0.0015 and liquidity["BSL"]:
        return {"direction": "SELL", "detail": "Rebote en línea de tendencia bajista con liquidez"}
    return None


STRATEGY_FUNCS = {
    1: _strategy_1_silver_bullet,
    2: _strategy_2_ob_mitigation,
    3: _strategy_3_amd_asian_range,
    4: _strategy_4_breakout,
    5: _strategy_5_ema_pullback,
    6: _strategy_6_ema_crossover,
    7: _strategy_7_stochastic_extreme,
    8: _strategy_8_bollinger,
    9: _strategy_9_vwap_reaction,
    10: _strategy_10_pin_bar,
    11: _strategy_11_engulfing,
    12: _strategy_12_rsi_divergence,
    13: _strategy_13_sniper_ob_fvg,
    14: _strategy_14_fibonacci_ote,
    15: _strategy_15_macd_cross,
    16: _strategy_16_volume_spike,
    17: _strategy_17_vsa,
    18: _strategy_18_dynamic_sr,
}

# CAMBIO (fix crítico, 2026-08-07): número MÁXIMO de estrategias asignadas a
# CUALQUIER grupo de activo (actualmente 2 en todos los grupos, ver
# ASSET_GROUPS arriba). signal_engine.py usa esta constante para no permitir
# nunca un `min_strategies` mayor a este valor -- un valor más alto (ej. el
# antiguo `min_indicators=6` que quedó guardado en trading_config.xlsx de la
# versión con 18 indicadores) haría que NINGUNA señal pudiera dispararse
# jamás, porque no hay forma de reunir 6 confirmaciones cuando el máximo
# posible es 2. Esto fue precisamente el bug que impidió que el sistema
# generara señales tras la migración: el Excel de configuración conservó el
# valor viejo (6) y signal_engine lo cargó sin validarlo contra el nuevo
# máximo real de estrategias por activo.
MAX_STRATEGIES_PER_ASSET = max(len(g["strategies"]) for g in ASSET_GROUPS.values())


class StrategyEngine:
    """Evalúa, para un activo dado, únicamente las estrategias óptimas asignadas a su grupo."""

    def evaluate(self, asset: str, df: pd.DataFrame) -> Tuple[str, int, List[str], Dict]:
        """
        Retorna (direction, strategies_confirmed, detail_list, extra) con
        la misma forma de uso que el antiguo `indicator_service.evaluate_signals`:
        - direction: "BUY" | "SELL" | "NEUTRAL"
        - strategies_confirmed: cuántas de las estrategias asignadas
          confirmaron esa misma dirección (para mantener el concepto de
          "min_indicators" -> ahora "min_strategies").
        - detail_list: descripciones legibles de qué confirmó.
        - extra: {"strategy_ids": [...], "pending": bool, "pending_reason": str}
        """
        strategy_ids = get_strategies_for_asset(asset)
        if df is None or df.empty or len(df) < 60:
            return "NEUTRAL", 0, [], {"strategy_ids": strategy_ids, "pending": False}

        votes = {"BUY": 0, "SELL": 0}
        details: List[str] = []
        confirmed_ids: List[int] = []

        for sid in strategy_ids:
            func = STRATEGY_FUNCS.get(sid)
            if func is None:
                continue
            try:
                result = func(df)
            except Exception as e:
                logger.debug(f"[strategy_engine] Estrategia {sid} falló para {asset}: {e}")
                result = None
            if result:
                votes[result["direction"]] += 1
                details.append(f"[Estrategia {sid} - {STRATEGY_NAMES.get(sid, '')}] {result['detail']}")
                confirmed_ids.append(sid)

        if votes["BUY"] == votes["SELL"]:
            direction = "NEUTRAL"
        elif votes["BUY"] > votes["SELL"]:
            direction = "BUY"
        else:
            direction = "SELL"

        strategies_confirmed = max(votes["BUY"], votes["SELL"])

        # "Pendiente de confirmación": una sola de las dos estrategias
        # asignadas dio señal, pero la otra todavía no -- candidato para el
        # Excel de "Señales por Confirmar" (ver excel_manager /
        # pending_signals_monitor.py), en vez de descartarse sin más.
        pending = strategies_confirmed == 1 and len(strategy_ids) >= 2

        return direction, strategies_confirmed, details, {
            "strategy_ids": strategy_ids,
            "confirmed_ids": confirmed_ids,
            "pending": pending,
        }

    def evaluate_independent(self, asset: str, df: pd.DataFrame) -> List[Dict]:
        """
        CAMBIO (a pedido del usuario, 2026-08-11 -- prueba comparativa de
        desempeño por estrategia, del 11 al 14/viernes): a diferencia de
        `evaluate()` (que exige que las 2 estrategias asignadas a un
        activo confirmen la MISMA dirección antes de generar una señal),
        este método evalúa cada estrategia asignada de forma
        COMPLETAMENTE INDEPENDIENTE. En cuanto UNA estrategia confirma,
        esa confirmación ya es suficiente -- no espera a la otra.

        Motivo: con el esquema anterior casi no había señales confirmadas
        (ver senales_por_confirmar.xlsx: 46 EXPIRADA, 0 CONFIRMADA que
        llegaran a generar señal real en varios días de prueba) porque en
        la práctica casi nunca coinciden las 2 estrategias de un mismo
        grupo al mismo tiempo. Además, el objetivo ahora es justamente
        MEDIR qué estrategia individual rinde mejor -- exigir que 2
        coincidan mezclaría los resultados y no permitiría comparar.

        Retorna una lista de resultados, uno por cada estrategia que
        confirmó en este ciclo (puede haber 0, 1, o hasta len(strategy_ids)
        resultados si varias confirman al mismo tiempo, incluso en
        direcciones opuestas -- cada una se trata como una señal
        independiente y candidata a su propio trade):
            [{"strategy_id": int, "strategy_name": str,
              "direction": "BUY"|"SELL", "detail": str}, ...]
        """
        strategy_ids = get_strategies_for_asset(asset)
        results: List[Dict] = []
        if df is None or df.empty or len(df) < 60:
            return results

        for sid in strategy_ids:
            func = STRATEGY_FUNCS.get(sid)
            if func is None:
                continue
            try:
                result = func(df)
            except Exception as e:
                logger.debug(f"[strategy_engine] Estrategia {sid} falló para {asset}: {e}")
                result = None
            if result:
                results.append({
                    "strategy_id": sid,
                    "strategy_name": STRATEGY_NAMES.get(sid, f"Estrategia {sid}"),
                    "direction": result["direction"],
                    "detail": result["detail"],
                })
        return results


strategy_engine = StrategyEngine()
