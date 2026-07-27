"""
Selector de estrategia: determina, por activo y en el momento actual,
cuál de las 4 estrategias del documento (ver `strategies.py`) es la más
adecuada según el régimen de mercado detectado.

Esto responde directamente a lo pedido por el usuario: "determina cual
estrategia es mejor para cada activo y en que momento aplica para cada
momento de la operativa". A diferencia de `strategies.py` (que evalúa
las 3 fases completas de entrada de cada estrategia), este módulo hace
un diagnóstico más liviano y rápido del RÉGIMEN de mercado actual
(tendencia fuerte / consolidación-squeeze / cerca de zona clave con
agotamiento / sesgo intradía claro), para recomendar qué estrategia
tiene más sentido probar en este momento, sin necesidad de esperar a
que las 3 fases completas ya hayan calzado.
"""
from typing import Dict, List
from loguru import logger

from app.services.market_data import market_data_service
from app.core.config import settings
from app.services import strategy_indicators as si


STRATEGY_LABELS = {
    "TREND_MTF": "Estrategia 1: Tendencia Multi-Timeframe",
    "BREAKOUT_VOLUME": "Estrategia 2: Ruptura con Confirmación de Volumen",
    "REVERSAL_ZONES": "Estrategia 3: Reversión en Zonas Clave",
    "SCALPING_TRIPLE": "Estrategia 4: Scalping con Triple Confirmación",
}


async def diagnose_regime(asset: str) -> Dict:
    """
    Diagnostica el régimen de mercado actual de un activo y recomienda
    la estrategia del documento más adecuada para ESTE momento.

    Retorna un dict con:
      - asset
      - recommended: nombre de la estrategia recomendada (o None)
      - reason: explicación breve de por qué
      - regime_scores: detalle de cada régimen detectado (para transparencia)
    """
    scores = {
        "is_trending": False,
        "is_squeeze": False,
        "is_near_key_zone_with_exhaustion": False,
        "has_clear_intraday_bias": False,
    }
    notes = []

    try:
        # --- Régimen 1: tendencia fuerte y reciente (D1) -> favorece Estrategia 1 ---
        df_daily = await market_data_service.get_time_series(asset, interval="1d", outputsize=120)
        if df_daily is not None and len(df_daily) >= 60:
            ema50 = si.calc_ema_series(df_daily, 50).iloc[-1]
            ema200 = si.calc_ema_series(df_daily, min(200, len(df_daily) - 1)).iloc[-1]
            structure = si.price_structure_trend(df_daily, lookback=8, order=2)
            aligned_bull = ema50 > ema200 and structure == "bullish"
            aligned_bear = ema50 < ema200 and structure == "bearish"
            scores["is_trending"] = bool(aligned_bull or aligned_bear)
            if scores["is_trending"]:
                notes.append(f"D1: EMA50/EMA200 y estructura de precio alineadas ({'alcista' if aligned_bull else 'bajista'})")

        # --- Régimen 2: squeeze de volatilidad (H4) -> favorece Estrategia 2 ---
        df_h4 = await market_data_service.get_time_series(asset, interval="4h", outputsize=100)
        if df_h4 is not None and len(df_h4) >= 30:
            squeeze = si.detect_bollinger_squeeze(df_h4)
            atr_compressed = si.atr_below_average(df_h4)
            scores["is_squeeze"] = bool(squeeze["is_squeeze"] and atr_compressed)
            if scores["is_squeeze"]:
                notes.append(f"H4: squeeze de volatilidad activo (percentil de banda {squeeze['percentile']:.0f}%)")

        # --- Régimen 3: precio cerca de zona clave con agotamiento -> favorece Estrategia 3 ---
        if df_daily is not None and len(df_daily) >= 40:
            swing_highs, swing_lows = si.detect_swing_points(df_daily, order=3)
            current_price = df_daily["close"].iloc[-1]
            atr_d1 = si.calc_atr_series(df_daily, 14).iloc[-1]
            all_points = [p for _, p in (swing_highs + swing_lows)]
            near_zone = any(abs(p - current_price) <= atr_d1 * 1.5 for p in all_points) if atr_d1 else False

            if near_zone and df_h4 is not None and len(df_h4) >= 40:
                rsi_h4 = si.calc_rsi_series(df_h4, 14)
                divergence = si.detect_regular_divergence(df_h4, rsi_h4, order=2, lookback=60)
                scores["is_near_key_zone_with_exhaustion"] = divergence is not None
                if scores["is_near_key_zone_with_exhaustion"]:
                    notes.append(f"D1/H4: precio cerca de zona clave con divergencia {divergence}")

        # --- Régimen 4: sesgo intradía claro (H1) -> favorece Estrategia 4 ---
        df_h1 = await market_data_service.get_time_series(asset, interval="1h", outputsize=60)
        if df_h1 is not None and len(df_h1) >= 20:
            ema50_h1 = si.calc_ema_series(df_h1, 50).iloc[-1]
            current_price_h1 = df_h1["close"].iloc[-1]
            structure_h1 = si.price_structure_trend(df_h1, lookback=6, order=1)
            bias = "bullish" if current_price_h1 > ema50_h1 else "bearish"
            scores["has_clear_intraday_bias"] = bool(structure_h1 == bias)
            if scores["has_clear_intraday_bias"]:
                notes.append(f"H1: sesgo intradía {bias} claro (precio vs EMA50 + estructura)")

    except Exception as e:
        logger.error(f"Error diagnosticando régimen para {asset}: {e}")

    # --- Decisión: prioridad cuando varios regímenes coinciden ---
    # Orden de prioridad: una reversión en zona clave con agotamiento es la
    # señal más específica/rara (se prioriza si aparece). Luego squeeze
    # (movimiento inminente). Luego tendencia sostenida. El sesgo intradía
    # de scalping se ofrece como complemento si no hay nada más específico,
    # ya que es el régimen más "común" (casi siempre hay algún sesgo H1).
    if scores["is_near_key_zone_with_exhaustion"]:
        recommended = "REVERSAL_ZONES"
        reason = "Precio en zona clave (soporte/resistencia con historial) mostrando agotamiento (divergencia) -- momento típico para buscar una reversión, no para perseguir la tendencia."
    elif scores["is_squeeze"]:
        recommended = "BREAKOUT_VOLUME"
        reason = "Volatilidad comprimida (squeeze) en H4 -- momento típico de acumulación antes de un movimiento explosivo; vigilar ruptura con volumen."
    elif scores["is_trending"]:
        recommended = "TREND_MTF"
        reason = "Tendencia macro (D1) alineada con la estructura de precio -- momento típico para buscar retrocesos y sumarse a favor de la tendencia."
    elif scores["has_clear_intraday_bias"]:
        recommended = "SCALPING_TRIPLE"
        reason = "Sin condición de tendencia/squeeze/reversión clara, pero hay un sesgo intradía (H1) definido -- apto solo para operativa rápida de scalping con gestión de riesgo estricta."
    else:
        recommended = None
        reason = "Ningún régimen de mercado claro detectado en este momento -- el documento recomienda NO forzar una operación cuando no hay una condición clara (ver 'Reglas generales', punto de journaling/backtesting)."

    return {
        "asset": asset,
        "recommended": recommended,
        "recommended_label": STRATEGY_LABELS.get(recommended) if recommended else None,
        "reason": reason,
        "regime_scores": scores,
        "notes": notes,
    }


async def recommend_for_all_assets() -> List[Dict]:
    """Corre `diagnose_regime` para cada activo en settings.ACTIVE_ASSETS."""
    results = []
    for asset in settings.ACTIVE_ASSETS:
        result = await diagnose_regime(asset)
        results.append(result)
    return results
