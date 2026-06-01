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
    CLOSED_TP1 = "CLOSED_TP1"
    CLOSED_TP2 = "CLOSED_TP2"
    CLOSED_TP3 = "CLOSED_TP3"
    CLOSED_SL = "CLOSED_SL"
    EXPIRED = "EXPIRED"


class Signal(BaseModel):
    """Trading signal model."""
    id: Optional[str] = None
    asset: str
    direction: SignalDirection
    entry_price: float
    stop_loss: float
    take_profit_1: float  # R:R 1:3
    take_profit_2: float  # R:R 1:6
    take_profit_3: float  # R:R 1:10
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
    indicators_detail: List[str] = []

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
