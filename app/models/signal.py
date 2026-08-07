"""Signal data models."""
import math
import uuid
from enum import Enum
from pydantic import BaseModel, Field
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
    # CAMBIO (defensa adicional, bug "no cierra las señales aunque sí manda
    # mensaje"): antes `id: Optional[str] = None` permitía crear un Signal
    # sin id en cualquier punto del código, lo que causaba fallos silenciosos
    # al intentar localizar la fila correcta en Excel para actualizar su
    # estado al cerrar (ver fix en signal_engine.py::_create_signal). Con
    # default_factory, incluso si algún otro punto del código construye un
    # Signal sin pasar id explícitamente, se genera uno único automáticamente
    # en vez de quedar en None.
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
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
    # CAMBIO (motor de estrategias): antes era 18 (total de indicadores
    # técnicos evaluados). Ahora representa cuántas estrategias SMC están
    # asignadas al grupo de ese activo (normalmente 2, ver
    # app/services/strategy_engine.py ASSET_GROUPS). Se pasa explícitamente
    # desde signal_engine.py, este default solo aplica si no se especifica.
    total_indicators: int = 2
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
    # Ticket de la posición en MetaTrader 5, si la ejecución en vivo está
    # habilitada (MT5_LIVE_TRADING_ENABLED=true). None si la señal es
    # solo informativa (no se envió orden real al bróker).
    mt5_ticket: Optional[int] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Signal":
        """
        Reconstruye un Signal desde un dict plano (típicamente una fila de
        Excel leída con pandas y convertida con `.to_dict('records')`).

        CAMBIO CRÍTICO (bug encontrado en auditoría exhaustiva): este método
        NO EXISTÍA. `SignalEngine._load_active_signals()` llamaba a
        `Signal.from_dict(record)` en un try/except que silenciaba el
        AttributeError resultante, dejando `active_signals` vacío cada vez
        que el proceso arrancaba con al menos una señal en estado ACTIVE en
        Excel. Como `position_monitor.py` depende enteramente de
        `signal_engine.active_signals` para evaluar SL/TP y cierres
        parciales, el efecto práctico era: cualquier posición abierta en el
        momento de un reinicio del proceso quedaba "huérfana" -- nunca más
        se evaluaba su SL/TP/cierre parcial automáticamente, aunque seguía
        bloqueando ese activo para nuevas señales (vía el chequeo directo a
        Excel en `_has_active_signal`).

        Se implementa tolerando valores NaN de pandas, `pandas.Timestamp`
        en vez de `datetime`, y columnas ausentes (usa los defaults del
        modelo).
        """
        clean = {}
        for key, value in data.items():
            if value is None:
                continue
            if isinstance(value, float) and math.isnan(value):
                continue
            if hasattr(value, "to_pydatetime"):  # pandas.Timestamp -> datetime
                value = value.to_pydatetime()
            clean[key] = value
        return cls(**clean)


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
