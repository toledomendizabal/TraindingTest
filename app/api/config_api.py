"""Configuration API endpoints."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
from app.services.excel_manager import excel_manager
from app.core.config import settings
from app.models.asset import ASSET_CATALOG

router = APIRouter()


class ConfigUpdate(BaseModel):
    """Configuration update schema."""
    assets: Optional[List[Dict[str, Any]]] = None
    parameters: Optional[Dict[str, Any]] = None
    indicators: Optional[List[Dict[str, Any]]] = None


class AssetToggle(BaseModel):
    """Toggle asset active status."""
    symbol: str
    active: bool


@router.get("/current")
async def get_current_config():
    """Get current trading configuration."""
    try:
        config = excel_manager.get_config()
        return config
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/update")
async def update_config(config: ConfigUpdate):
    """Update trading configuration."""
    try:
        update_data = {}
        if config.assets is not None:
            update_data["assets"] = config.assets
        if config.parameters is not None:
            update_data["parameters"] = config.parameters
        if config.indicators is not None:
            update_data["indicators"] = config.indicators

        success = excel_manager.update_config(update_data)
        if success:
            # Update runtime settings
            if config.parameters:
                if "initial_capital" in config.parameters:
                    settings.INITIAL_CAPITAL = float(config.parameters["initial_capital"])
                if "risk_percentage" in config.parameters:
                    settings.RISK_PERCENTAGE = float(config.parameters["risk_percentage"])

            return {"status": "success", "message": "Configuration updated"}
        else:
            raise HTTPException(status_code=500, detail="Failed to update configuration")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/assets/toggle")
async def toggle_asset(data: AssetToggle):
    """Toggle an asset's active status."""
    try:
        config = excel_manager.get_config()
        assets = config.get("assets", [])

        for asset in assets:
            if asset["symbol"] == data.symbol:
                asset["active"] = data.active
                break
        else:
            # Add new asset
            from app.models.asset import Asset
            pip_info = Asset.get_pip_info(data.symbol)
            assets.append({
                "symbol": data.symbol,
                "active": data.active,
                "pip_size": pip_info["pip_size"],
                "contract_size": pip_info["contract_size"]
            })

        excel_manager.update_config({"assets": assets})

        # Update runtime active assets
        settings.ACTIVE_ASSETS = [a["symbol"] for a in assets if a.get("active", True)]

        return {"status": "success", "active_assets": settings.ACTIVE_ASSETS}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/available-assets")
async def get_available_assets():
    """Get all available assets organized by category."""
    return {
        "forex": settings.AVAILABLE_FOREX,
        "commodities": settings.AVAILABLE_COMMODITIES,
        "indices": settings.AVAILABLE_INDICES,
        "active": settings.ACTIVE_ASSETS
    }


@router.get("/trading-mode")
async def get_trading_mode():
    """Get current trading mode (offline/online)."""
    return {
        "mode": "offline",
        "description": "Excel-based monitoring (MetaTrader not connected)",
        "metatrader_available": False
    }


@router.put("/trading-mode")
async def set_trading_mode(mode: str = "offline"):
    """Set trading mode."""
    # For now, only offline mode is supported
    return {
        "mode": mode,
        "message": "Trading mode updated. MetaTrader integration requires additional setup."
    }
