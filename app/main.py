"""Main FastAPI application entry point."""
import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from loguru import logger
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.api.router import api_router
from app.services.scheduler import scheduler_service
from app.services.position_monitor import position_monitor
from app.services.mt4_monitor import mt4_monitor


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

    # Start MT4 Offline Monitor
    if settings.MT4_SYNC_ENABLED:
        await mt4_monitor.start()

    logger.info(f"Active assets: {settings.ACTIVE_ASSETS}")
    logger.info(f"Capital: ${settings.INITIAL_CAPITAL}")
    logger.info(f"Risk: {settings.RISK_PERCENTAGE}%")
    logger.info("System ready!")

    yield

    # Shutdown
    logger.info("Shutting down TradingSignal Pro...")
    scheduler_service.stop()
    await position_monitor.stop_monitoring()
    await mt4_monitor.stop()
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

# --- Serve frontend static files ---
# Support both Vite (dist/) and CRA (build/) output directories
frontend_build_dir = os.path.join(settings.BASE_DIR, "frontend", "build")
frontend_dist_dir = os.path.join(settings.BASE_DIR, "frontend", "dist")

# Determine which frontend directory exists
frontend_dir = None
if os.path.exists(frontend_dist_dir) and os.path.isfile(os.path.join(frontend_dist_dir, "index.html")):
    frontend_dir = frontend_dist_dir
elif os.path.exists(frontend_build_dir) and os.path.isfile(os.path.join(frontend_build_dir, "index.html")):
    frontend_dir = frontend_build_dir

if frontend_dir:
    # Mount static/assets directory if it exists
    static_dir = os.path.join(frontend_dir, "static")
    assets_dir = os.path.join(frontend_dir, "assets")

    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve React frontend for any non-API route."""
        # Skip API routes
        if full_path.startswith("api/"):
            return None

        # Try to serve the exact file
        file_path = os.path.join(frontend_dir, full_path)
        if full_path and os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)

        # Fallback to index.html for SPA routing
        return FileResponse(os.path.join(frontend_dir, "index.html"))

    logger.info(f"Frontend served from: {frontend_dir}")
else:
    @app.get("/")
    async def root():
        """Root endpoint when frontend is not built."""
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>TradingSignal Pro</title>
            <style>
                body { font-family: Arial, sans-serif; background: #1a1a2e; color: #e0e0e0; 
                       display: flex; justify-content: center; align-items: center; 
                       min-height: 100vh; margin: 0; }
                .container { text-align: center; padding: 40px; }
                h1 { color: #00d4aa; font-size: 2.5em; }
                .status { color: #4caf50; font-size: 1.2em; margin: 20px 0; }
                a { color: #00d4aa; text-decoration: none; font-size: 1.1em; }
                a:hover { text-decoration: underline; }
                .info { background: #16213e; padding: 20px; border-radius: 10px; margin: 20px 0; }
                code { background: #0f3460; padding: 3px 8px; border-radius: 4px; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>TradingSignal Pro</h1>
                <p class="status">&#10003; API Running</p>
                <div class="info">
                    <p><a href="/docs">&#128203; API Documentation (Swagger)</a></p>
                    <p><a href="/api/dashboard/overview">&#128200; Dashboard Data</a></p>
                    <p><a href="/api/signals/active">&#128226; Active Signals</a></p>
                </div>
                <div class="info">
                    <p><strong>Frontend no compilado.</strong></p>
                    <p>Para habilitar el dashboard, ejecute:</p>
                    <p><code>cd frontend && npm install && npm run build</code></p>
                </div>
            </div>
        </body>
        </html>
        """, status_code=200)

    logger.info("Frontend not built. API-only mode. Visit /docs for API documentation.")
