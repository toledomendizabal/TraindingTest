"""Dashboard API endpoints."""
from fastapi import APIRouter, HTTPException
from typing import Dict
from app.services.excel_manager import excel_manager
from app.services.market_data import market_data_service
from app.services.scheduler import scheduler_service
from app.core.config import settings

router = APIRouter()


@router.get("/overview")
async def get_dashboard_overview():
    """Get dashboard overview data."""
    try:
        stats = excel_manager.get_statistics()
        active_signals = excel_manager.get_active_signals()

        # Get current prices for active assets
        prices = {}
        for asset in settings.ACTIVE_ASSETS[:5]:  # Limit to avoid rate limiting
            price = market_data_service.get_cached_price(asset)
            if price:
                prices[asset] = price

        return {
            "statistics": stats,
            "active_signals": active_signals,
            "prices": prices,
            "session": market_data_service.get_current_session(),
            "active_assets": settings.ACTIVE_ASSETS,
            "system_status": "running"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kpis")
async def get_kpis():
    """Get Key Performance Indicators."""
    try:
        stats = excel_manager.get_statistics()

        return {
            "win_rate": {
                "value": stats["win_rate"],
                "target": 75.0,
                "status": "good" if stats["win_rate"] >= 55 else "warning"
            },
            "profit_factor": {
                "value": stats["profit_factor"],
                "target": 1.5,
                "status": "good" if stats["profit_factor"] >= 1.5 else "warning"
            },
            "drawdown": {
                "value": 0,  # Calculate from history
                "target": 10.0,
                "status": "good"
            },
            "total_signals": stats["total_signals"],
            "active_signals": stats["active_signals"],
            "net_profit": stats["net_profit"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scheduler/status")
async def get_scheduler_status():
    """Get scheduler jobs status."""
    try:
        jobs = scheduler_service.get_jobs_status()
        return {"jobs": jobs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs")
async def get_recent_logs(lines: int = 50):
    """Get recent system logs."""
    try:
        import os
        from datetime import datetime

        log_dir = settings.LOGS_DIR
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(log_dir, f"system_{today}.log")

        if os.path.exists(log_file):
            with open(log_file, "r") as f:
                all_lines = f.readlines()
                return {"logs": all_lines[-lines:]}

        return {"logs": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
