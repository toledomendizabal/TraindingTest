"""API endpoints for chart data."""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Optional
from app.services.market_data import market_data_service
from app.services.signal_engine import signal_engine
from datetime import datetime

router = APIRouter()

@router.get("/candles/{asset}")
async def get_candles(
    asset: str,
    interval: str = Query("5m", regex="^(1m|5m|15m|1h|1d)$"),
    outputsize: int = Query(200, ge=50, le=2000)
):
    """Get candlestick data for an asset."""
    try:
        df = await market_data_service.get_time_series(asset, interval=interval, outputsize=outputsize)
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"No data found for {asset}")
        
        # Format for Lightweight Charts
        candles = []
        for _, row in df.iterrows():
            candles.append({
                "time": int(row["datetime"].timestamp()),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 0))
            })
        
        return {
            "asset": asset,
            "interval": interval,
            "candles": candles
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/markers/{asset}")
async def get_chart_markers(asset: str):
    """Get markers (Entry, TP, SL) for active signals of an asset."""
    active_signals = signal_engine.get_active_signals()
    markers = []
    
    for signal in active_signals:
        if signal.asset == asset:
            # Entry marker
            markers.append({
                "time": int(signal.created_at.timestamp()) if signal.created_at else int(datetime.now().timestamp()),
                "position": "belowBar" if signal.direction.value == "BUY" else "aboveBar",
                "color": "#22c55e" if signal.direction.value == "BUY" else "#ef4444",
                "shape": "arrowUp" if signal.direction.value == "BUY" else "arrowDown",
                "text": f"ENTRY @ {signal.entry_price}",
                "price": signal.entry_price
            })
            
            # Lines (these will be handled differently in frontend as PriceLines)
            markers.append({
                "type": "price_line",
                "price": signal.stop_loss,
                "color": "#ef4444",
                "title": "SL"
            })
            markers.append({
                "type": "price_line",
                "price": signal.take_profit_3,
                "color": "#22c55e",
                "title": "TP3"
            })
            
    return markers
