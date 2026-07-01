"""Signal data models."""
from enum import Enum
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class SignalDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class SignalStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CLOSED_TP1 = "CLOSED_TP1"          # Cierre total en TP1 (legacy / sin partials)
    CLOSED_TP2 = "CLOSED_TP2"          # Cierre total en TP2 (legacy / sin partials)
    CLOSED_TP3 = "CLOSED_TP3"          # Cierre final tras pasar por TP1 y TP2 parciales
    CLOSED_SL = "CLOSED_SL"            # Stop Loss original alcanzado (pérdida total)
    CLOSED_BE = "CLOSED_BE"            # SL movido a breakeven tras TP1 y alcanzado (ganancia parcial protegida, sin pérdida)
    EXPIRED = "EXPIRED"


class Signal(BaseModel):
    """Trading signal model."""
    id: Optional[str] = None
    asset: str
    direction: SignalDirection
    entry_price: float
    stop_loss: float
    take_profit_1: float  # TP1 = 1R (cierra TP1_CLOSE_PCT%, mueve SL a breakeven)
    take_profit_2: float  # TP2 = 2R (cierra TP2_CLOSE_PCT%, mueve SL a TP1)
    take_profit_3: float  # TP3 = 3R (cierra el remanente)
    sl_pips: float
    tp1_pips: float
    tp2_pips: float
    tp3_pips: float
    lot_size: float
    timeframe: str = "5m"
    indicators_met: int = 0
    total_indicators: int = 18
    score: float = 0.0
    status: SignalStatus = SignalStatus.ACTIVE
    session: str = ""  # Tokyo, London, NewYork
    created_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    profit_loss: float = 0.0
    close_price: Optional[float] = None
    # New institutional metrics
    max_drawdown: float = 0.0
    risk_reward_ratio: float = 0.0
    duration_minutes: float = 0.0
    entry_hour: Optional[str] = None
    exit_hour: Optional[str] = None
    entry_spread: float = 0.0
    entry_atr: float = 0.0
    smc_quality: float = 1.0
    fvg_confluence: bool = False
    liquidity_sweep: bool = False
    indicators_detail: List[str] = []
    # --- Partial close / scaled exit tracking (CAMBIO: TP1/TP2/TP3 reales) ---
    initial_lot_size: float = 0.0       # Lotaje original (para referencia, lot_size queda como remanente)
    remaining_lot_size: float = 0.0     # Lotaje aún abierto
    tp1_hit: bool = False
    tp2_hit: bool = False
    breakeven_active: bool = False      # True si el SL ya fue movido a entry_price (o mejor)
    realized_partial_pnl: float = 0.0   # P/L ya materializado por cierres parciales (TP1/TP2)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class SignalCreate(BaseModel):
    """Schema for creating a new signal."""
    asset: str
    direction: SignalDirection
    entry_price: float
    stop_loss: float
    timeframe: str = "5m"


class BacktestResult(BaseModel):
    """Backtesting result model."""
    date: str
    total_signals: int = 0
    winning_signals: int = 0
    losing_signals: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    total_profit: float = 0.0
    total_loss: float = 0.0
    net_profit: float = 0.0
    recommendations: List[str] = []
    indicator_adjustments: List[str] = []
