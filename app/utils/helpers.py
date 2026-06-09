"""Utility helper functions."""
from datetime import datetime
from typing import Dict


def calculate_lot_size(capital: float, risk_pct: float, sl_pips: float,
                       pip_value: float, contract_size: float, 
                       quote_to_base_rate: float = 1.0) -> float:
    """
    Calculate position lot size based on risk management.
    
    quote_to_base_rate: Exchange rate to convert quote currency to account currency (USD).
    Example for GER40 (EUR): rate would be EURUSD price.
    Example for USD pairs: rate is 1.0.
    """
    risk_amount = capital * (risk_pct / 100)
    
    # Pip value in account currency (USD)
    # If quote is EUR and account is USD, pip_value_usd = pip_value_eur * EURUSD
    pip_value_usd = pip_value * quote_to_base_rate
    pip_value_per_lot = pip_value_usd * contract_size

    if pip_value_per_lot <= 0 or sl_pips <= 0:
        return 0.01

    lot_size = risk_amount / (sl_pips * pip_value_per_lot)
    
    # Round to 2 decimals for standard MT4/MT5 lots
    return round(max(0.01, min(lot_size, 100.0)), 2)


def calculate_pips(price1: float, price2: float, pip_size: float) -> float:
    """Calculate pip difference between two prices."""
    return abs(price1 - price2) / pip_size


def get_trading_session() -> Dict[str, str]:
    """Get current trading session information."""
    now = datetime.utcnow()
    hour = now.hour

    sessions = {
        "Tokyo": {"start": 0, "end": 8, "emoji": "JP"},
        "London": {"start": 8, "end": 13, "emoji": "GB"},
        "NewYork": {"start": 13, "end": 22, "emoji": "US"}
    }

    current = "Tokyo"
    for name, times in sessions.items():
        if times["start"] <= hour < times["end"]:
            current = name
            break

    return {
        "name": current,
        "utc_hour": hour,
        "local_time": now.strftime("%H:%M:%S UTC")
    }


def format_signal_message(signal) -> str:
    """Format a signal for display."""
    return (
        f"{signal.asset} | {signal.direction.value} | "
        f"Entry: {signal.entry_price} | SL: {signal.stop_loss} | "
        f"TP1: {signal.take_profit_1} | Score: {signal.score}%"
    )


def validate_asset_symbol(symbol: str) -> bool:
    """Validate if a symbol is recognized."""
    from app.models.asset import ASSET_CATALOG
    return symbol in ASSET_CATALOG
