"""
Monitor de 'Señales por Confirmar'.

Revisa periódicamente `excel/senales_por_confirmar.xlsx` (creado y
mantenido por `excel_manager`). Para cada fila PENDIENTE:

1. Si ya expiró (created_at + settings.PENDING_SIGNALS_EXPIRY_MINUTES),
   se marca EXPIRADA y no se activa nada.
2. Si no ha expirado, se vuelve a evaluar el activo con
   `strategy_engine.evaluate()`. Si la(s) estrategia(s) que faltaban ya
   confirman la MISMA dirección, la fila se marca CONFIRMADA y se llama a
   `signal_engine.analyze_asset()` para que la señal se genere y pase por
   el pipeline normal (spread, sesión, estructura, macro, Excel principal,
   MT5) exactamente igual que una señal directa.

Uso: se agenda igual que el resto de tareas en `scheduler.py`, por
ejemplo cada `settings.PENDING_SIGNALS_CHECK_INTERVAL_SECONDS` segundos.
No reemplaza a `analyze_all_assets()` -- corre en paralelo, solo para las
señales que quedaron a medias.
"""
from datetime import datetime
from loguru import logger

from app.core.config import settings
from app.services.excel_manager import excel_manager
from app.services.market_data import market_data_service
from app.services.strategy_engine import strategy_engine


async def check_pending_signals():
    """Revisa todas las señales PENDIENTES y confirma o expira cada una."""
    pending_rows = excel_manager.get_open_pending_signals()
    if not pending_rows:
        return

    now = datetime.now()
    checked = 0
    confirmed = 0
    expired = 0

    for row in pending_rows:
        checked += 1
        asset = row.get("asset")
        direction = row.get("direction")
        pending_id = row.get("id")

        try:
            expires_at = datetime.fromisoformat(row.get("expires_at"))
        except Exception:
            expires_at = None

        if expires_at and now >= expires_at:
            excel_manager.resolve_pending_signal(pending_id, "EXPIRADA")
            expired += 1
            logger.info(f"[PENDIENTE->EXPIRADA] {asset} {direction} (id={pending_id}): venció sin segunda confirmación.")
            continue

        try:
            df = await market_data_service.get_time_series(
                asset, interval=settings.SIGNAL_TIMEFRAME if hasattr(settings, "SIGNAL_TIMEFRAME") else "5m",
                outputsize=200,
            )
        except Exception as e:
            logger.debug(f"[PENDIENTE] {asset}: no se pudo re-evaluar ({e}), se revisa en el próximo ciclo.")
            continue

        if df is None or df.empty:
            continue

        new_direction, strategies_confirmed, details, extra = strategy_engine.evaluate(asset, df)

        if new_direction == direction and strategies_confirmed >= 2:
            excel_manager.resolve_pending_signal(pending_id, "CONFIRMADA")
            confirmed += 1
            logger.info(f"[PENDIENTE->CONFIRMADA] {asset} {direction} (id={pending_id}): segunda estrategia confirmó. Generando señal real...")
            # Import diferido para evitar import circular (signal_engine importa excel_manager).
            from app.services.signal_engine import signal_engine
            await signal_engine.analyze_asset(asset)
        elif new_direction not in (direction, "NEUTRAL"):
            # La dirección se invirtió por completo: ya no tiene sentido
            # mantenerla viva, se descarta como expirada.
            excel_manager.resolve_pending_signal(pending_id, "EXPIRADA")
            expired += 1
            logger.info(f"[PENDIENTE->EXPIRADA] {asset}: la dirección cambió de {direction} a {new_direction}, se descarta.")

    if checked:
        logger.info(f"[MONITOR PENDIENTES] Revisadas {checked} señal(es) por confirmar -> {confirmed} confirmada(s), {expired} expirada(s).")
