"""API endpoints para las 4 estrategias de trading multi-timeframe (ver strategies.py / strategy_selector.py)."""
from fastapi import APIRouter, HTTPException
from app.services.strategy_selector import diagnose_regime, recommend_for_all_assets, STRATEGY_LABELS
from app.services.strategies import strategy_engine
from app.core.config import settings

router = APIRouter()


@router.get("/recommendations")
async def get_strategy_recommendations():
    """
    Para cada activo en ACTIVE_ASSETS, diagnostica el régimen de mercado
    actual y recomienda cuál de las 4 estrategias del documento aplica
    en este momento (o ninguna, si no hay una condición clara).
    """
    try:
        results = await recommend_for_all_assets()
        return {"strategies": STRATEGY_LABELS, "recommendations": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recommendations/{asset}")
async def get_strategy_recommendation_for_asset(asset: str):
    """Diagnóstico de régimen y estrategia recomendada para un único activo."""
    if asset not in settings.ACTIVE_ASSETS:
        raise HTTPException(status_code=404, detail=f"{asset} no está en ACTIVE_ASSETS")
    try:
        result = await diagnose_regime(asset)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/evaluate/{asset}")
async def evaluate_strategies_for_asset(asset: str):
    """
    Corre la evaluación COMPLETA de las 3 fases (Dirección/Confirmación/
    Entrada) de las 4 estrategias para un activo, y devuelve cualquier
    candidato de señal que haya superado las 3 fases en este momento
    (puede ser ninguno, uno, o varios).
    """
    if asset not in settings.ACTIVE_ASSETS:
        raise HTTPException(status_code=404, detail=f"{asset} no está en ACTIVE_ASSETS")
    try:
        candidates = await strategy_engine.evaluate_all(asset)
        return {
            "asset": asset,
            "candidates_found": len(candidates),
            "candidates": [
                {
                    "strategy": c.strategy,
                    "direction": c.direction,
                    "entry_price": c.entry_price,
                    "stop_loss": c.stop_loss,
                    "take_profit_1": c.take_profit_1,
                    "take_profit_2": c.take_profit_2,
                    "risk_reward_min": c.risk_reward_min,
                    "risk_pct": c.risk_pct,
                    "details": c.details,
                }
                for c in candidates
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
