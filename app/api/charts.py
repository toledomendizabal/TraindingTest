"""API endpoints for chart data."""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Optional
import pandas as pd
from app.services.market_data import market_data_service
from app.services.signal_engine import signal_engine
from app.services.indicators import indicator_service
from datetime import datetime
from loguru import logger

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
        
        # Calculate EMAs for visual confirmation
        ema50 = df["close"].ewm(span=50, adjust=False).mean()
        ema200 = df["close"].ewm(span=200, adjust=False).mean()

        # Format for Lightweight Charts
        candles = []
        ema50_data = []
        ema200_data = []
        
        for i, row in df.iterrows():
            ts = int(row["datetime"].timestamp())
            candles.append({
                "time": ts,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 0))
            })
            
            if not pd.isna(ema50.iloc[i]):
                ema50_data.append({"time": ts, "value": float(ema50.iloc[i])})
            if not pd.isna(ema200.iloc[i]):
                ema200_data.append({"time": ts, "value": float(ema200.iloc[i])})
        
        # Final check to avoid NaN in JSON
        result = {
            "asset": asset,
            "interval": interval,
            "candles": candles,
            "ema50": ema50_data,
            "ema200": ema200_data
        }
        
        logger.debug(f"Returning {len(candles)} candles for {asset}")
        return result
        
    except Exception as e:
        logger.error(f"Error in candles API for {asset}: {e}")
        raise HTTPException(status_code=500, detail=f"Chart Error: {str(e)}")

@router.get("/markers/{asset}")
async def get_chart_markers(asset: str, interval: str = "5m"):
    """Get markers (Entry, TP, SL, FVG, Liquidity) for an asset."""
    active_signals = signal_engine.get_active_signals()
    markers = []
    
    # 1. Active Trade Markers
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
                "price": signal.take_profit_1,
                "color": "#22c55e",
                "title": "TP1"
            })
            markers.append({
                "type": "price_line",
                "price": signal.take_profit_3,
                "color": "#22c55e",
                "title": "TP3"
            })

    # 2. SMC Structural Markers (FVG & Liquidity)
    try:
        df = await market_data_service.get_time_series(asset, interval=interval, outputsize=100)
        if df is not None and not df.empty:
            fvgs = indicator_service.detect_fvg(df)
            liquidity = indicator_service.detect_liquidity(df)
            
            # Add FVG lines
            for fvg in fvgs[-5:]: # Only last 5
                markers.append({
                    "type": "price_line",
                    "price": fvg["price"],
                    "color": "#3b82f6" if fvg["type"] == "BULLISH" else "#f97316",
                    "title": f"FVG {fvg['type'][:4]}"
                })
                
            # Add Liquidity lines
            if liquidity["BSL"]:
                markers.append({
                    "type": "price_line",
                    "price": max(liquidity["BSL"]),
                    "color": "#eab308",
                    "title": "BSL"
                })
            if liquidity["SSL"]:
                markers.append({
                    "type": "price_line",
                    "price": min(liquidity["SSL"]),
                    "color": "#a855f7",
                    "title": "SSL"
                })
    except Exception as e:
        logger.error(f"Error adding SMC markers: {e}")
            
    return markers
