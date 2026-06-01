"""Main FastAPI application entry point."""
import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from loguru import logger
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.api.router import api_router
from app.services.scheduler import scheduler_service
from app.services.position_monitor import position_monitor


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("=" * 60)
    logger.info("TradingSignal Pro - Starting System")
    logger.info("=" * 60)

    # Ensure directories exist
    os.makedirs(settings.EXCEL_DIR, exist_ok=True)
    os.makedirs(settings.LOGS_DIR, exist_ok=True)
    os.makedirs(settings.REPORTS_DIR, exist_ok=True)
    os.makedirs(settings.CONFIG_DIR, exist_ok=True)

    # Initialize Excel files
    from app.services.excel_manager import excel_manager
    excel_manager._ensure_files()

    # Start scheduler
    scheduler_service.start()

    # Start position monitor in background
    asyncio.create_task(position_monitor.start_monitoring())

    logger.info(f"Active assets: {settings.ACTIVE_ASSETS}")
    logger.info(f"Capital: ${settings.INITIAL_CAPITAL}")
    logger.info(f"Risk: {settings.RISK_PERCENTAGE}%")
    logger.info("System ready!")

    yield

    # Shutdown
    logger.info("Shutting down TradingSignal Pro...")
    scheduler_service.stop()
    await position_monitor.stop_monitoring()
    from app.services.market_data import market_data_service
    await market_data_service.close()
    logger.info("System shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="TradingSignal Pro",
    description="Sistema Inteligente de Señales de Trading Multi-Activo",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api")

# Serve frontend static files
frontend_dir = os.path.join(settings.BASE_DIR, "frontend", "build")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=os.path.join(frontend_dir, "static")), name="static")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve React frontend."""
        file_path = os.path.join(frontend_dir, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dir, "index.html"))
else:
    @app.get("/")
    async def root():
        """Root endpoint when frontend is not built."""
        return {
            "message": "TradingSignal Pro API",
            "version": "1.0.0",
            "docs": "/docs",
            "status": "running"
        }
