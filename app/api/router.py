"""Main API router combining all endpoints."""
from fastapi import APIRouter
from app.api.signals import router as signals_router
from app.api.dashboard import router as dashboard_router
from app.api.config_api import router as config_router
from app.api.backtesting_api import router as backtest_router
from app.api.auth import router as auth_router
from app.api.websocket_api import router as ws_router
from app.api.charts import router as charts_router

api_router = APIRouter()

api_router.include_router(signals_router, prefix="/signals", tags=["Signals"])
api_router.include_router(charts_router, prefix="/charts", tags=["Charts"])
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(config_router, prefix="/config", tags=["Configuration"])
api_router.include_router(backtest_router, prefix="/backtesting", tags=["Backtesting"])
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(ws_router, prefix="/ws", tags=["WebSocket"])
