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
        # JPY pairs
        if "JPY" in symbol:
            return {"pip_value": 0.01, "pip_size": 0.01, "contract_size": 100000.0}
        # Gold
        elif symbol in ["XAUUSD", "GOLD"]:
            return {"pip_value": 0.01, "pip_size": 0.01, "contract_size": 100.0}
        # Indices
        elif "Cash" in symbol or symbol in ["US30", "US100", "US500", "GER40"]:
            return {"pip_value": 1.0, "pip_size": 1.0, "contract_size": 1.0}
        # Standard forex
        else:
            return {"pip_value": 0.0001, "pip_size": 0.0001, "contract_size": 100000.0}


# Predefined asset catalog
ASSET_CATALOG = {
    # Forex
    "EURUSD": Asset(symbol="EURUSD", name="Euro / US Dollar", asset_type=AssetType.FOREX, pip_value=0.0001, pip_size=0.0001),
    "GBPUSD": Asset(symbol="GBPUSD", name="British Pound / US Dollar", asset_type=AssetType.FOREX, pip_value=0.0001, pip_size=0.0001),
    "USDJPY": Asset(symbol="USDJPY", name="US Dollar / Japanese Yen", asset_type=AssetType.FOREX, pip_value=0.01, pip_size=0.01),
    "USDCHF": Asset(symbol="USDCHF", name="US Dollar / Swiss Franc", asset_type=AssetType.FOREX, pip_value=0.0001, pip_size=0.0001),
    "USDCAD": Asset(symbol="USDCAD", name="US Dollar / Canadian Dollar", asset_type=AssetType.FOREX, pip_value=0.0001, pip_size=0.0001),
    "NZDUSD": Asset(symbol="NZDUSD", name="New Zealand Dollar / US Dollar", asset_type=AssetType.FOREX, pip_value=0.0001, pip_size=0.0001),
    "AUDUSD": Asset(symbol="AUDUSD", name="Australian Dollar / US Dollar", asset_type=AssetType.FOREX, pip_value=0.0001, pip_size=0.0001),
    "EURGBP": Asset(symbol="EURGBP", name="Euro / British Pound", asset_type=AssetType.FOREX, pip_value=0.0001, pip_size=0.0001),
    "EURJPY": Asset(symbol="EURJPY", name="Euro / Japanese Yen", asset_type=AssetType.FOREX, pip_value=0.01, pip_size=0.01),
    "GBPJPY": Asset(symbol="GBPJPY", name="British Pound / Japanese Yen", asset_type=AssetType.FOREX, pip_value=0.01, pip_size=0.01),
    # Commodities
    "XAUUSD": Asset(symbol="XAUUSD", name="Gold / US Dollar", asset_type=AssetType.COMMODITY, pip_value=0.01, pip_size=0.01, contract_size=100.0),
    "XAGUSD": Asset(symbol="XAGUSD", name="Silver / US Dollar", asset_type=AssetType.COMMODITY, pip_value=0.001, pip_size=0.001, contract_size=5000.0),
    # Indices
    "US30Cash": Asset(symbol="US30Cash", name="Dow Jones 30", asset_type=AssetType.INDEX, pip_value=1.0, pip_size=1.0, contract_size=1.0),
    "US100Cash": Asset(symbol="US100Cash", name="Nasdaq 100", asset_type=AssetType.INDEX, pip_value=1.0, pip_size=1.0, contract_size=1.0),
    "US500Cash": Asset(symbol="US500Cash", name="S&P 500", asset_type=AssetType.INDEX, pip_value=1.0, pip_size=1.0, contract_size=1.0),
    "GER40Cash": Asset(symbol="GER40Cash", name="DAX 40", asset_type=AssetType.INDEX, pip_value=1.0, pip_size=1.0, contract_size=1.0),
}
