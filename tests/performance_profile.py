import time
import os
import psutil
import asyncio
import pandas as pd
import numpy as np
from loguru import logger
from app.services.indicators import indicator_service
from app.services.signal_engine import SignalEngine

def get_memory_usage():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024  # MB

async def profile_performance():
    print("=== PERFILADO DE RENDIMIENTO DEL SISTEMA ===")
    
    start_mem = get_memory_usage()
    print(f"Memoria inicial: {start_mem:.2f} MB")
    
    # Simulate processing 50 assets to see memory growth
    num_assets = 50
    print(f"Simulando procesamiento de {num_assets} activos...")
    
    # Create dummy data for 50 assets
    dummy_data = pd.DataFrame({
        'datetime': pd.date_range(start='2026-01-01', periods=1000, freq='5min'),
        'open': np.random.uniform(2000, 2100, 1000),
        'high': np.random.uniform(2100, 2200, 1000),
        'low': np.random.uniform(1900, 2000, 1000),
        'close': np.random.uniform(2000, 2100, 1000),
        'volume': np.random.uniform(100, 1000, 1000)
    })
    
    start_time = time.time()
    
    for i in range(num_assets):
        # Calculate indicators
        indicators = indicator_service.calculate_all(dummy_data)
        # Evaluate signals
        indicator_service.evaluate_signals(dummy_data, indicators)
        
        if (i + 1) % 10 == 0:
            current_mem = get_memory_usage()
            print(f"Procesados {i+1}/{num_assets} activos. Memoria: {current_mem:.2f} MB (+{current_mem - start_mem:.2f} MB)")
            
    end_time = time.time()
    end_mem = get_memory_usage()
    
    print("\n=== RESULTADOS FINALES ===")
    print(f"Tiempo total: {end_time - start_time:.2f} segundos")
    print(f"Tiempo por activo: {(end_time - start_time) / num_assets:.4f} segundos")
    print(f"Memoria final: {end_mem:.2f} MB")
    print(f"Incremento total de memoria: {end_mem - start_mem:.2f} MB")
    
    if end_mem - start_mem > 50:
        print("ADVERTENCIA: Posible fuga de memoria o alto consumo en procesamiento de DataFrames.")
    else:
        print("RENDIMIENTO: Consumo de memoria estable.")

if __name__ == "__main__":
    asyncio.run(profile_performance())
