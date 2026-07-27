"""
Indicadores y utilidades auxiliares para las 4 estrategias de trading
multi-timeframe descritas en "Guía Detallada: 4 Estrategias de Trading
Multi-Timeframe" (documento aportado por el usuario, 2026-07-23).

Este módulo complementa a `indicators.py` (que ya cubre EMA, RSI, MACD,
Bollinger, ATR, FVG, liquidez) con las piezas específicas que las 4
estrategias necesitan y que no existían: estructura de precio (máximos/
mínimos crecientes o decrecientes), niveles de Fibonacci, detección de
squeeze de Bollinger, divergencias RSI/MACD, rango de consolidación,
patrones de vela (envolvente, pin bar), volumen relativo, y remuestreo a
semanal.

Todas las funciones son puras (reciben un DataFrame OHLC y devuelven un
resultado), sin dependencia de estado ni de la configuración en runtime,
para que sean fáciles de probar de forma aislada.
"""
from typing import Optional, Dict, List, Tuple
import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# Series de indicadores (a diferencia de indicators.py, que en su mayoría
# solo devuelve el último valor, aquí necesitamos la SERIE completa para
# detectar cruces, divergencias, y "salir de una zona" en vez de solo
# "tocarla").
# ---------------------------------------------------------------------------

def calc_ema_series(df: pd.DataFrame, period: int) -> pd.Series:
    return df["close"].ewm(span=period, adjust=False).mean()


def calc_rsi_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    # CAMBIO (bug encontrado en pruebas propias): cuando hay una racha
    # puramente alcista dentro de la ventana, loss=0 legítimamente (no
    # hubo velas bajistas), y el RSI correcto en ese caso es 100 (máximo
    # momentum alcista) -- no NaN. Dividir gain/0 sin este manejo
    # explícito, o reemplazar 0 por NaN para "evitar la división",
    # produce NaN en vez de 100 justo en los tramos de impulso más fuerte,
    # que son exactamente los que importan para detectar divergencias.
    rsi = pd.Series(index=df.index, dtype=float)
    both_zero = (gain == 0) & (loss == 0)
    loss_zero = (loss == 0) & (gain > 0)
    normal = ~both_zero & ~loss_zero

    rs = gain[normal] / loss[normal]
    rsi[normal] = 100 - (100 / (1 + rs))
    rsi[loss_zero] = 100.0
    rsi[both_zero] = 50.0
    return rsi


def calc_macd_series(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, pd.Series]:
    ema_fast = calc_ema_series(df, fast)
    ema_slow = calc_ema_series(df, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return {"macd": macd_line, "signal": signal_line, "histogram": histogram}


def calc_atr_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    tr1 = df["high"] - df["low"]
    tr2 = abs(df["high"] - df["close"].shift(1))
    tr3 = abs(df["low"] - df["close"].shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()


# ---------------------------------------------------------------------------
# Estructura de precio y swings
# ---------------------------------------------------------------------------

def detect_swing_points(df: pd.DataFrame, order: int = 3) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
    """
    Detecta swing highs / swing lows: una vela cuyo high (o low) es el
    máximo (o mínimo) dentro de una ventana de `order` velas a cada lado.

    Retorna (swing_highs, swing_lows), cada uno como lista de tuplas
    (índice_en_df, precio), ordenadas por índice ascendente.
    """
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)

    swing_highs = []
    swing_lows = []

    for i in range(order, n - order):
        window_highs = highs[i - order: i + order + 1]
        if highs[i] == window_highs.max() and np.argmax(window_highs) == order:
            swing_highs.append((i, float(highs[i])))

        window_lows = lows[i - order: i + order + 1]
        if lows[i] == window_lows.min() and np.argmin(window_lows) == order:
            swing_lows.append((i, float(lows[i])))

    return swing_highs, swing_lows


def price_structure_trend(df: pd.DataFrame, lookback: int = 8, order: int = 2) -> str:
    """
    Estrategia 1, Fase 1: "la estructura de precio debe mostrar máximos y
    mínimos crecientes (alcista) o decrecientes (bajista) en las últimas
    5-8 velas".

    Retorna "bullish", "bearish", o "neutral".

    Usa primero la detección estricta de swing highs/lows (más fiel al
    texto del documento). Si esa detección es inconclusa -- por ejemplo,
    con retrocesos de una sola vela que no llegan a formar picos/valles
    limpios bajo la ventana `order` -- usa como respaldo la pendiente de
    una regresión lineal simple sobre los cierres del lookback, que es
    más robusta a este tipo de ruido y sigue reflejando fielmente si la
    tendencia reciente es ascendente o descendente.
    """
    recent = df.tail(lookback + order * 2)
    swing_highs, swing_lows = detect_swing_points(recent, order=order)

    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        highs_rising = swing_highs[-1][1] > swing_highs[-2][1]
        lows_rising = swing_lows[-1][1] > swing_lows[-2][1]
        highs_falling = swing_highs[-1][1] < swing_highs[-2][1]
        lows_falling = swing_lows[-1][1] < swing_lows[-2][1]

        if highs_rising and lows_rising:
            return "bullish"
        if highs_falling and lows_falling:
            return "bearish"
        return "neutral"

    # Respaldo: pendiente de regresión lineal sobre los cierres recientes
    closes = df["close"].tail(lookback).values
    if len(closes) < 3:
        return "neutral"
    x = np.arange(len(closes))
    slope = np.polyfit(x, closes, 1)[0]
    avg_price = closes.mean()
    # Umbral relativo: la pendiente debe representar un movimiento de al
    # menos ~0.05% del precio promedio a lo largo del lookback para
    # considerarse una tendencia real, no ruido.
    threshold = avg_price * 0.0005 / lookback
    if slope > threshold:
        return "bullish"
    if slope < -threshold:
        return "bearish"
    return "neutral"


# ---------------------------------------------------------------------------
# Fibonacci
# ---------------------------------------------------------------------------

def fibonacci_levels(swing_high: float, swing_low: float) -> Dict[str, float]:
    """
    Niveles de retroceso de Fibonacci del impulso [swing_low, swing_high]
    (para un impulso alcista; para uno bajista se interpreta al revés).
    """
    diff = swing_high - swing_low
    return {
        "0.382": swing_high - 0.382 * diff,
        "0.5": swing_high - 0.5 * diff,
        "0.618": swing_high - 0.618 * diff,
        "0.786": swing_high - 0.786 * diff,
        "1.618_ext": swing_high + 0.618 * diff,  # proyección para TP2 (Estrategia 1)
    }


def last_impulse_fibonacci(df: pd.DataFrame, lookback: int = 50, order: int = 3) -> Optional[Dict]:
    """
    Encuentra el último impulso relevante (entre el swing low y el swing
    high más recientes, o viceversa) y calcula sus niveles de Fibonacci.
    Retorna None si no hay suficientes swings detectables.
    """
    recent = df.tail(lookback)
    swing_highs, swing_lows = detect_swing_points(recent, order=order)
    if not swing_highs or not swing_lows:
        return None

    last_high = swing_highs[-1]
    last_low = swing_lows[-1]

    # Impulso alcista: el low es más viejo que el high (el precio subió)
    if last_low[0] < last_high[0]:
        levels = fibonacci_levels(last_high[1], last_low[1])
        return {"direction": "bullish", "swing_high": last_high[1], "swing_low": last_low[1], "levels": levels}
    else:
        # Impulso bajista: el high es más viejo que el low (el precio bajó)
        levels = fibonacci_levels(last_high[1], last_low[1])
        return {"direction": "bearish", "swing_high": last_high[1], "swing_low": last_low[1], "levels": levels}


# ---------------------------------------------------------------------------
# Squeeze de volatilidad (Estrategia 2, Fase 1)
# ---------------------------------------------------------------------------

def detect_bollinger_squeeze(df: pd.DataFrame, period: int = 20, std_dev: float = 2, percentile_window: int = 20) -> Dict:
    """
    "Bandas de Bollinger (20,2) con ancho de banda en el percentil más
    bajo de los últimos 20 periodos (squeeze)."

    Retorna {"is_squeeze": bool, "bandwidth": float, "percentile": float}
    """
    sma = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    bandwidth = (upper - lower) / sma

    recent_bw = bandwidth.tail(percentile_window)
    if recent_bw.isna().all() or len(recent_bw.dropna()) < 5:
        return {"is_squeeze": False, "bandwidth": None, "percentile": None}

    current_bw = bandwidth.iloc[-1]
    percentile = float((recent_bw < current_bw).sum() / len(recent_bw.dropna()) * 100)

    return {
        "is_squeeze": percentile <= 20,  # está entre el 20% más bajo de las últimas N lecturas
        "bandwidth": float(current_bw) if pd.notna(current_bw) else None,
        "percentile": percentile,
    }


def atr_below_average(df: pd.DataFrame, period: int = 14, avg_window: int = 20) -> bool:
    """"ATR(14) de H4 por debajo de su media de 20 periodos -> volatilidad comprimida."""
    atr = calc_atr_series(df, period)
    avg = atr.rolling(avg_window).mean()
    if pd.isna(atr.iloc[-1]) or pd.isna(avg.iloc[-1]):
        return False
    return bool(atr.iloc[-1] < avg.iloc[-1])


# ---------------------------------------------------------------------------
# Rango de consolidación (Estrategia 2)
# ---------------------------------------------------------------------------

def detect_consolidation_range(df: pd.DataFrame, min_candles: int = 5, lookback: int = 20) -> Optional[Dict]:
    """
    Marca el techo y piso de un rango de consolidación: usa las últimas
    `min_candles` (hasta `lookback`) velas ANTERIORES a la vela actual y
    calcula su high/low. Es una aproximación simple y verificable del
    "rango de consolidación" del documento, sin asumir un detector de
    clusters más sofisticado.
    """
    if len(df) < min_candles + 1:
        return None

    window = df.iloc[-(lookback + 1):-1] if len(df) > lookback + 1 else df.iloc[:-1]
    if len(window) < min_candles:
        return None

    range_high = float(window["high"].max())
    range_low = float(window["low"].min())
    return {"high": range_high, "low": range_low, "num_candles": len(window)}


# ---------------------------------------------------------------------------
# Divergencias regulares (Estrategia 3)
# ---------------------------------------------------------------------------

def detect_regular_divergence(df: pd.DataFrame, indicator_series: pd.Series, order: int = 2, lookback: int = 40) -> Optional[str]:
    """
    Divergencia regular: el precio marca un nuevo extremo, pero el
    indicador (RSI o histograma MACD) marca uno MENOS extremo.

    Retorna "bullish" (posible reversión al alza), "bearish" (posible
    reversión a la baja), o None si no hay divergencia clara con al
    menos 2 picos/valles.
    """
    recent_df = df.tail(lookback).reset_index(drop=True)
    recent_ind = indicator_series.tail(lookback).reset_index(drop=True)

    swing_highs, swing_lows = detect_swing_points(recent_df, order=order)

    # Divergencia bajista: 2 máximos de precio, el segundo más alto,
    # pero el indicador en el segundo máximo es más bajo.
    if len(swing_highs) >= 2:
        i1, p1 = swing_highs[-2]
        i2, p2 = swing_highs[-1]
        if p2 > p1 and i2 < len(recent_ind) and i1 < len(recent_ind):
            ind1, ind2 = recent_ind.iloc[i1], recent_ind.iloc[i2]
            if pd.notna(ind1) and pd.notna(ind2) and ind2 < ind1:
                return "bearish"

    # Divergencia alcista: 2 mínimos de precio, el segundo más bajo,
    # pero el indicador en el segundo mínimo es más alto.
    if len(swing_lows) >= 2:
        i1, p1 = swing_lows[-2]
        i2, p2 = swing_lows[-1]
        if p2 < p1 and i2 < len(recent_ind) and i1 < len(recent_ind):
            ind1, ind2 = recent_ind.iloc[i1], recent_ind.iloc[i2]
            if pd.notna(ind1) and pd.notna(ind2) and ind2 > ind1:
                return "bullish"

    return None


# ---------------------------------------------------------------------------
# Patrones de vela
# ---------------------------------------------------------------------------

def is_bullish_engulfing(df: pd.DataFrame) -> bool:
    if len(df) < 2:
        return False
    prev, cur = df.iloc[-2], df.iloc[-1]
    return bool(
        prev["close"] < prev["open"]  # vela previa bajista
        and cur["close"] > cur["open"]  # vela actual alcista
        and cur["close"] >= prev["open"]
        and cur["open"] <= prev["close"]
    )


def is_bearish_engulfing(df: pd.DataFrame) -> bool:
    if len(df) < 2:
        return False
    prev, cur = df.iloc[-2], df.iloc[-1]
    return bool(
        prev["close"] > prev["open"]  # vela previa alcista
        and cur["close"] < cur["open"]  # vela actual bajista
        and cur["close"] <= prev["open"]
        and cur["open"] >= prev["close"]
    )


def is_pin_bar(df: pd.DataFrame, wick_ratio: float = 2.0) -> Optional[str]:
    """
    Pin bar: mecha larga (al menos `wick_ratio` veces el cuerpo) de un
    lado, cuerpo pequeño. Retorna "bullish" (mecha inferior larga),
    "bearish" (mecha superior larga), o None.
    """
    if len(df) < 1:
        return None
    c = df.iloc[-1]
    body = abs(c["close"] - c["open"])
    if body == 0:
        body = (c["high"] - c["low"]) * 0.01  # evitar división por cero en velas doji perfectas
    upper_wick = c["high"] - max(c["close"], c["open"])
    lower_wick = min(c["close"], c["open"]) - c["low"]

    if lower_wick >= wick_ratio * body and lower_wick > upper_wick:
        return "bullish"
    if upper_wick >= wick_ratio * body and upper_wick > lower_wick:
        return "bearish"
    return None


def is_impulse_candle(df: pd.DataFrame, body_ratio: float = 0.6) -> Optional[str]:
    """Estrategia 4: "vela de impulso con cuerpo > 60% del rango total"."""
    if len(df) < 1:
        return None
    c = df.iloc[-1]
    total_range = c["high"] - c["low"]
    if total_range <= 0:
        return None
    body = abs(c["close"] - c["open"])
    if (body / total_range) > body_ratio:
        return "bullish" if c["close"] > c["open"] else "bearish"
    return None


# ---------------------------------------------------------------------------
# Volumen relativo y remuestreo semanal
# ---------------------------------------------------------------------------

def relative_volume(df: pd.DataFrame, lookback: int = 20) -> float:
    """Volumen de la última vela / promedio de las `lookback` anteriores. 1.0 si no hay datos de volumen."""
    if "volume" not in df.columns or df["volume"].sum() == 0 or len(df) < lookback + 1:
        return 1.0
    avg_vol = df["volume"].iloc[-(lookback + 1):-1].mean()
    if avg_vol == 0 or pd.isna(avg_vol):
        return 1.0
    return float(df["volume"].iloc[-1] / avg_vol)


def resample_to_weekly(df_daily: pd.DataFrame) -> pd.DataFrame:
    """Remuestrea velas diarias a semanales (usado para la Fase 1 de las Estrategias 1 y 3, que piden W1)."""
    d = df_daily.copy()
    d["datetime"] = pd.to_datetime(d["datetime"])
    d = d.set_index("datetime")
    weekly = d.resample("W").agg({
        "open": "first", "high": "max", "low": "min", "close": "last",
        "volume": "sum" if "volume" in d.columns else "last"
    }).dropna()
    weekly = weekly.reset_index()
    return weekly
