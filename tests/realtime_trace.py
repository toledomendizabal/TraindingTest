
import asyncio
import os
import sys
from datetime import datetime

# Añadir el directorio raíz al path para poder importar la app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.signal_engine import signal_engine
from app.services.market_data import market_data_service
from app.core.config import settings

async def trace_signals():
    print(f"--- INICIANDO RASTREO DE SEÑALES ({datetime.now()}) ---")
    print(f"Configuración cargada: Min Indicators = {signal_engine.min_indicators}")
    print(f"Timeframe: {signal_engine.signal_timeframe}")
    print(f"Activos activos: {settings.ACTIVE_ASSETS}")
    
    for asset in settings.ACTIVE_ASSETS:
        print(f"\n>>> Analizando {asset}...")
        
        # 1. Verificar si hay señal activa
        if signal_engine._has_active_signal(asset):
            print(f"  [BLOQUEO] Ya existe una señal activa o cooldown para {asset}")
            continue
            
        # 2. Verificar datos
        df = await market_data_service.get_time_series(asset, interval=signal_engine.signal_timeframe)
        if df is None or df.empty:
            print(f"  [ERROR] No hay datos históricos para {asset}")
            continue
        print(f"  [OK] Datos cargados: {len(df)} velas. Última vela: {df['datetime'].iloc[-1]}")
        
        # 3. Evaluar indicadores
        from app.services.indicators import indicator_service
        indicators = indicator_service.calculate_all(df)
        if not indicators:
            print(f"  [ERROR] Fallo al calcular indicadores para {asset}")
            continue
            
        direction, indicators_met, details = indicator_service.evaluate_signals(df, indicators)
        print(f"  [INFO] Dirección: {direction}, Indicadores cumplidos: {indicators_met}/{signal_engine.min_indicators}")
        
        if direction == "NEUTRAL" or indicators_met < signal_engine.min_indicators:
            print(f"  [RECHAZO] No cumple confluencia mínima.")
            continue
            
        # 4. Verificar validación estructural
        print(f"  [INFO] Pasando a validación estructural (HTF)...")
        confirmations = 0
        for tf in ["30m", "1h", "4h"]:
            df_tf = await market_data_service.get_time_series(asset, interval=tf)
            if df_tf is not None:
                from app.services.indicators import indicator_service
                ema200 = df_tf["close"].ewm(span=200, adjust=False).mean().iloc[-1]
                curr = df_tf["close"].iloc[-1]
                ok = (direction == "BUY" and curr > ema200) or (direction == "SELL" and curr < ema200)
                print(f"    - {tf}: {'ALINEADO' if ok else 'NO ALINEADO'} (Precio: {curr}, EMA200: {round(ema200, 5)})")
                if ok: confirmations += 1
        
        # 5. Verificar FVG en 30m
        df_30m = await market_data_service.get_time_series(asset, interval="30m")
        if df_30m is not None:
            fvgs = indicator_service.detect_fvg(df_30m)
            recent_fvgs = fvgs[-10:]
            has_fvg = any(f["type"] == ("BULLISH" if direction == "BUY" else "BEARISH") for f in recent_fvgs)
            print(f"    - FVG 30m: {'ENCONTRADO' if has_fvg else 'NO ENCONTRADO'}")

    print("\n--- RASTREO FINALIZADO ---")

if __name__ == "__main__":
    asyncio.run(trace_signals())
