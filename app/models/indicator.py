"""Indicator configuration models."""
from pydantic import BaseModel
from typing import Dict, Any, List


class IndicatorConfig(BaseModel):
    """Configuration for a technical indicator."""
    name: str
    enabled: bool = True
    parameters: Dict[str, Any] = {}
    category: str = ""  # trend, momentum, volatility, volume
    weight: float = 1.0


# Default indicator configurations based on PRD
DEFAULT_INDICATORS = [
    # Trend Indicators (Layer 1 - Direction)
    IndicatorConfig(
        name="EMA_200",
        category="trend",
        parameters={"period": 200, "source": "close"},
        weight=1.5
    ),
    IndicatorConfig(
        name="EMA_50",
        category="trend",
        parameters={"period": 50, "source": "close"},
        weight=1.2
    ),
    IndicatorConfig(
        name="EMA_20",
        category="trend",
        parameters={"period": 20, "source": "close"},
        weight=1.0
    ),
    IndicatorConfig(
        name="EMA_9",
        category="trend",
        parameters={"period": 9, "source": "close"},
        weight=1.0
    ),
    IndicatorConfig(
        name="PARABOLIC_SAR",
        category="trend",
        parameters={"step": 0.02, "max_step": 0.2},
        weight=0.8 # Reduced weight, can be noisy in choppy markets
    ),
    IndicatorConfig(
        name="ICHIMOKU",
        category="trend",
        parameters={"tenkan": 9, "kijun": 26, "senkou_b": 52},
        weight=1.3
    ),
    IndicatorConfig(
        name="ADX_DMI",
        category="trend",
        parameters={"period": 14, "threshold": 30}, # Increased threshold for stronger trend confirmation
        weight=1.2
    ),
    # Momentum Indicators (Layer 3 - Triggers)
    IndicatorConfig(
        name="RSI",
        category="momentum",
        parameters={"period": 14, "overbought": 75, "oversold": 25}, # Stricter overbought/oversold levels
        weight=1.3
    ),
    IndicatorConfig(
        name="STOCHASTIC",
        category="momentum",
        parameters={"k_period": 14, "d_period": 3, "slowing": 3, "overbought": 85, "oversold": 15}, # Stricter overbought/oversold levels
        weight=1.0
    ),
    IndicatorConfig(
        name="MACD",
        category="momentum",
        parameters={"fast": 12, "slow": 26, "signal": 9},
        weight=1.3
    ),
    IndicatorConfig(
        name="CCI",
        category="momentum",
        parameters={"period": 20, "upper": 100, "lower": -100},
        weight=1.0
    ),
    IndicatorConfig(
        name="AWESOME_OSCILLATOR",
        category="momentum",
        parameters={"fast": 5, "slow": 34},
        weight=0.8
    ),
    # Volatility Indicators (Layer 2 - Value Zones)
    IndicatorConfig(
        name="BOLLINGER_BANDS",
        category="volatility",
        parameters={"period": 20, "std_dev": 2},
        weight=1.2
    ),
    IndicatorConfig(
        name="WILLIAMS_R",
        category="volatility",
        parameters={"period": 14, "overbought": -20, "oversold": -80},
        weight=1.0
    ),
    IndicatorConfig(
        name="KELTNER_CHANNELS",
        category="volatility",
        parameters={"ema_period": 20, "atr_multiplier": 2},
        weight=1.0
    ),
    IndicatorConfig(
        name="ATR",
        category="volatility",
        parameters={"period": 14, "sl_multiplier": 1.5},
        weight=1.0
    ),
    # Volume Indicators (Layer 4 - Flow)
    IndicatorConfig(
        name="VOLUME_MA",
        category="volume",
        parameters={"period": 20},
        weight=1.0
    ),
    IndicatorConfig(
        name="MFI",
        category="volume",
        parameters={"period": 14, "overbought": 80, "oversold": 20},
        weight=1.0
    ),
]


def get_default_indicators() -> List[IndicatorConfig]:
    """Return default indicator configurations."""
    return DEFAULT_INDICATORS.copy()
