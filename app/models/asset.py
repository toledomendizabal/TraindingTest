"""Asset data models."""
from enum import Enum
from pydantic import BaseModel
from typing import Optional


class AssetType(str, Enum):
    FOREX = "FOREX"
    COMMODITY = "COMMODITY"
    INDEX = "INDEX"


class Asset(BaseModel):
    """Trading asset model."""
    symbol: str
    name: str
    asset_type: AssetType
    active: bool = True
    pip_value: float = 0.0001  # Default for forex
    pip_size: float = 0.0001
    contract_size: float = 100000.0  # Standard lot

    @classmethod
    def get_pip_info(cls, symbol: str) -> dict:
        """Get pip value and size for a given symbol."""
        symbol_upper = symbol.upper().replace("/", "")
        
        # JPY pairs: Pip is 2nd decimal (0.01)
        if "JPY" in symbol_upper:
            return {"pip_value": 0.01, "pip_size": 0.01, "contract_size": 100000.0, "quote_currency": "JPY"}
        
        # Gold (XAUUSD): Pip is 2nd decimal (0.01). 1.00 movement = 100 pips.
        elif any(x in symbol_upper for x in ["XAU", "GOLD"]):
            return {"pip_value": 0.01, "pip_size": 0.01, "contract_size": 100.0, "quote_currency": "USD"}
            
        # Silver (XAGUSD): Pip is 3rd decimal (0.001).
        elif any(x in symbol_upper for x in ["XAG", "SILVER"]):
            return {"pip_value": 0.001, "pip_size": 0.001, "contract_size": 5000.0, "quote_currency": "USD"}
            
        # Petróleo (WTI/BRENT/USOIL/UKOIL): pip = 2do decimal (0.01)
        elif any(x in symbol_upper for x in ["WTI", "BRENT", "USOIL", "UKOIL", "OIL"]):
            return {"pip_value": 0.01, "pip_size": 0.01, "contract_size": 1000.0, "quote_currency": "USD"}

        # Cobre (COPPER): pip = 4to decimal, típico en la mayoría de brokers
        elif "COPPER" in symbol_upper:
            return {"pip_value": 0.0001, "pip_size": 0.0001, "contract_size": 25000.0, "quote_currency": "USD"}

        # Indices (US30, US100, US500): Pip = Point = 1.0
        elif any(x in symbol_upper for x in ["US30", "US100", "US500", "DJI", "NAS", "SPX"]):
            return {"pip_value": 1.0, "pip_size": 1.0, "contract_size": 1.0, "quote_currency": "USD"}
            
        # GER40 (DAX) / STOXX50: Pip = Point = 1.0, cotizan en EUR
        elif any(x in symbol_upper for x in ["GER40", "DAX", "STOXX50", "STOXX"]):
            return {"pip_value": 1.0, "pip_size": 1.0, "contract_size": 1.0, "quote_currency": "EUR"}
            
        # Standard forex: Pip is 4th decimal (0.0001)
        else:
            quote = symbol_upper[-3:] if len(symbol_upper) >= 6 else "USD"
            return {"pip_value": 0.0001, "pip_size": 0.0001, "contract_size": 100000.0, "quote_currency": quote}


# Predefined asset catalog
ASSET_CATALOG = {
    # --- Forex: Majors ---
    "EURUSD": Asset(symbol="EURUSD", name="Euro / US Dollar", asset_type=AssetType.FOREX, pip_value=0.0001, pip_size=0.0001),
    "GBPUSD": Asset(symbol="GBPUSD", name="British Pound / US Dollar", asset_type=AssetType.FOREX, pip_value=0.0001, pip_size=0.0001),
    "USDCHF": Asset(symbol="USDCHF", name="US Dollar / Swiss Franc", asset_type=AssetType.FOREX, pip_value=0.0001, pip_size=0.0001),
    "NZDUSD": Asset(symbol="NZDUSD", name="New Zealand Dollar / US Dollar", asset_type=AssetType.FOREX, pip_value=0.0001, pip_size=0.0001),
    # --- Forex: Yen & Commodity ---
    "USDJPY": Asset(symbol="USDJPY", name="US Dollar / Japanese Yen", asset_type=AssetType.FOREX, pip_value=0.01, pip_size=0.01),
    "AUDUSD": Asset(symbol="AUDUSD", name="Australian Dollar / US Dollar", asset_type=AssetType.FOREX, pip_value=0.0001, pip_size=0.0001),
    "USDCAD": Asset(symbol="USDCAD", name="US Dollar / Canadian Dollar", asset_type=AssetType.FOREX, pip_value=0.0001, pip_size=0.0001),
    # --- Forex: Cruces / Minors ---
    "EURGBP": Asset(symbol="EURGBP", name="Euro / British Pound", asset_type=AssetType.FOREX, pip_value=0.0001, pip_size=0.0001),
    "EURJPY": Asset(symbol="EURJPY", name="Euro / Japanese Yen", asset_type=AssetType.FOREX, pip_value=0.01, pip_size=0.01),
    "EURCHF": Asset(symbol="EURCHF", name="Euro / Swiss Franc", asset_type=AssetType.FOREX, pip_value=0.0001, pip_size=0.0001),
    "GBPJPY": Asset(symbol="GBPJPY", name="British Pound / Japanese Yen", asset_type=AssetType.FOREX, pip_value=0.01, pip_size=0.01),
    "CHFJPY": Asset(symbol="CHFJPY", name="Swiss Franc / Japanese Yen", asset_type=AssetType.FOREX, pip_value=0.01, pip_size=0.01),
    "AUDJPY": Asset(symbol="AUDJPY", name="Australian Dollar / Japanese Yen", asset_type=AssetType.FOREX, pip_value=0.01, pip_size=0.01),
    "CADJPY": Asset(symbol="CADJPY", name="Canadian Dollar / Japanese Yen", asset_type=AssetType.FOREX, pip_value=0.01, pip_size=0.01),
    "NZDJPY": Asset(symbol="NZDJPY", name="New Zealand Dollar / Japanese Yen", asset_type=AssetType.FOREX, pip_value=0.01, pip_size=0.01),
    "AUDNZD": Asset(symbol="AUDNZD", name="Australian Dollar / New Zealand Dollar", asset_type=AssetType.FOREX, pip_value=0.0001, pip_size=0.0001),
    "AUDCHF": Asset(symbol="AUDCHF", name="Australian Dollar / Swiss Franc", asset_type=AssetType.FOREX, pip_value=0.0001, pip_size=0.0001),
    "GBPCHF": Asset(symbol="GBPCHF", name="British Pound / Swiss Franc", asset_type=AssetType.FOREX, pip_value=0.0001, pip_size=0.0001),
    "CADCHF": Asset(symbol="CADCHF", name="Canadian Dollar / Swiss Franc", asset_type=AssetType.FOREX, pip_value=0.0001, pip_size=0.0001),
    # --- Materias Primas y Metales ---
    "XAUUSD": Asset(symbol="XAUUSD", name="Gold / US Dollar", asset_type=AssetType.COMMODITY, pip_value=0.01, pip_size=0.01, contract_size=100.0),
    "XAGUSD": Asset(symbol="XAGUSD", name="Silver / US Dollar", asset_type=AssetType.COMMODITY, pip_value=0.001, pip_size=0.001, contract_size=5000.0),
    "WTI": Asset(symbol="WTI", name="WTI Crude Oil", asset_type=AssetType.COMMODITY, pip_value=0.01, pip_size=0.01, contract_size=1000.0),
    "BRENT": Asset(symbol="BRENT", name="Brent Crude Oil", asset_type=AssetType.COMMODITY, pip_value=0.01, pip_size=0.01, contract_size=1000.0),
    "COPPER": Asset(symbol="COPPER", name="Copper", asset_type=AssetType.COMMODITY, pip_value=0.0001, pip_size=0.0001, contract_size=25000.0),
    # --- Índices Bursátiles ---
    "US30Cash": Asset(symbol="US30Cash", name="Dow Jones 30", asset_type=AssetType.INDEX, pip_value=1.0, pip_size=1.0, contract_size=1.0),
    "US100Cash": Asset(symbol="US100Cash", name="Nasdaq 100", asset_type=AssetType.INDEX, pip_value=1.0, pip_size=1.0, contract_size=1.0),
    "US500Cash": Asset(symbol="US500Cash", name="S&P 500", asset_type=AssetType.INDEX, pip_value=1.0, pip_size=1.0, contract_size=1.0),
    "GER40Cash": Asset(symbol="GER40Cash", name="DAX 40", asset_type=AssetType.INDEX, pip_value=1.0, pip_size=1.0, contract_size=1.0),
    "STOXX50Cash": Asset(symbol="STOXX50Cash", name="Euro Stoxx 50", asset_type=AssetType.INDEX, pip_value=1.0, pip_size=1.0, contract_size=1.0),
}
