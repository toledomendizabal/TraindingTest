"""Backtesting API endpoints."""
from fastapi import APIRouter, HTTPException
from app.services.backtesting import backtesting_service

router = APIRouter()


@router.get("/reports")
async def get_all_reports():
    """Get list of all backtesting reports."""
    try:
        reports = backtesting_service.get_all_reports()
        return {"reports": reports}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report/latest")
async def get_latest_report(report_type: str = "daily"):
    """Get the latest backtesting report."""
    try:
        report = backtesting_service.get_latest_report(report_type)
        if report:
            return {"report": report, "type": report_type}
        return {"report": None, "message": "No reports available"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run/daily")
async def trigger_daily_backtest():
    """Manually trigger daily backtesting."""
    try:
        result = await backtesting_service.run_daily_backtest()
        return {"status": "success", "result": result.model_dump()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run/weekly")
async def trigger_weekly_backtest():
    """Manually trigger weekly backtesting."""
    try:
        result = await backtesting_service.run_weekly_backtest()
        return {"status": "success", "result": result.model_dump()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
