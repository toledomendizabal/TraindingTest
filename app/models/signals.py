"""Signals API endpoints."""
from fastapi import APIRouter, HTTPException
from typing import List, Optional
from app.services.signal_engine import signal_engine
from app.services.excel_manager import excel_manager, _sanitize_list
from app.models.signal import Signal

router = APIRouter()


@router.get("/active", response_model=List[dict])
async def get_active_signals():
    """Get all active trading signals."""
    try:
        signals = excel_manager.get_active_signals()
        return signals
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/all")
async def get_all_signals():
    """Get all signals (active and closed)."""
    try:
        df = excel_manager.get_signals_dataframe()
        if df.empty:
            return []
        # CAMBIO (bug encontrado al probar el filtro de estrategia en el
        # dashboard, 2026-07-27): `df.to_dict("records")` sin sanitizar
        # devuelve valores NaN de pandas para cualquier columna vacía (ej.
        # closed_at, exit_hour en señales activas), y el encoder JSON por
        # defecto de FastAPI/Starlette NO acepta NaN ("Out of range float
        # values are not JSON compliant") -- el endpoint completo
        # devolvía un 500 en cuanto había AL MENOS una señal con algún
        # campo vacío, lo cual es prácticamente siempre. El frontend lo
        # tragaba en silencio (catch -> deja la lista vacía), mostrando
        # "Sin señales registradas" sin ningún error visible. Se
        # reutiliza el mismo sanitizador que ya usan get_active/get_closed.
        return _sanitize_list(df.to_dict("records"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/closed")
async def get_closed_signals(start_date: Optional[str] = None):
    """Get closed signals, optionally filtered by date."""
    try:
        signals = excel_manager.get_closed_signals(start_date)
        return signals
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze")
async def trigger_analysis():
    """Manually trigger signal analysis for all assets."""
    try:
        signals = await signal_engine.analyze_all_assets()
        return {
            "status": "success",
            "signals_generated": len(signals),
            "signals": [s.model_dump() for s in signals]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/{asset}")
async def analyze_single_asset(asset: str):
    """Analyze a single asset."""
    try:
        signal = await signal_engine.analyze_asset(asset)
        if signal:
            return {"status": "signal_generated", "signal": signal.model_dump()}
        return {"status": "no_signal", "message": f"No signal generated for {asset}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
async def get_statistics():
    """Get trading statistics."""
    try:
        stats = excel_manager.get_statistics()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
