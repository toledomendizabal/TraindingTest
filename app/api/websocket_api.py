"""WebSocket API for real-time data streaming."""
import asyncio
import json
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List, Dict
from loguru import logger
from app.services.market_data import market_data_service
from app.services.excel_manager import excel_manager
from app.core.config import settings

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept and store a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


@router.websocket("/live")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for live data streaming."""
    await manager.connect(websocket)

    try:
        while True:
            # Send updates every 2 seconds
            data = await _get_live_data()
            await websocket.send_json(data)
            await asyncio.sleep(2)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@router.websocket("/prices")
async def prices_websocket(websocket: WebSocket):
    """WebSocket endpoint for price streaming."""
    await manager.connect(websocket)

    try:
        while True:
            prices = {}
            for asset in settings.ACTIVE_ASSETS:
                price = market_data_service.get_cached_price(asset)
                if price:
                    prices[asset] = price

            await websocket.send_json({
                "type": "prices",
                "data": prices,
                "timestamp": datetime.now().isoformat()
            })
            await asyncio.sleep(1)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


async def _get_live_data() -> Dict:
    """Get live dashboard data for WebSocket broadcast."""
    try:
        stats = excel_manager.get_statistics()
        active_signals = excel_manager.get_active_signals()

        prices = {}
        for asset in settings.ACTIVE_ASSETS[:6]:
            price = market_data_service.get_cached_price(asset)
            if price:
                prices[asset] = price

        return {
            "type": "dashboard_update",
            "timestamp": datetime.now().isoformat(),
            "data": {
                "statistics": stats,
                "active_signals": active_signals[:10],
                "prices": prices,
                "session": market_data_service.get_current_session()
            }
        }
    except Exception as e:
        return {
            "type": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }
