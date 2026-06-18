import asyncio
import pandas as pd
import numpy as np
from app.services.indicators import indicator_service
from app.services.signal_engine import SignalEngine
from app.models.indicator import DEFAULT_INDICATORS

async def audit():
    print("=== AUDIT DE SEÑALES TRADING PRO ===")
    
    # 1. Verificar Pesos y Umbrales
    total_weight = sum(ind.weight for ind in DEFAULT_INDICATORS if ind.enabled)
    min_ind = SignalEngine.MIN_INDICATORS_FOR_SIGNAL
    num_ind = len([ind for ind in DEFAULT_INDICATORS if ind.enabled])
    
    # El umbral de score se calcula en indicators.py:
    # min_score_for_signal = max_possible_score * (min_indicators / len(self.indicators))
    min_score = total_weight * (min_ind / num_ind)
    
    print(f"Indicadores Activos: {num_ind}")
    print(f"Mínimo Indicadores Requeridos: {min_ind}")
    print(f"Peso Total Posible: {total_weight:.2f}")
    print(f"Score Mínimo Requerido (Umbral): {min_score:.2f}")
    
    # 2. Simular un Escenario de Mercado (Bullish fuerte)
    # Creamos un dataframe donde casi todo sea alcista
    df = pd.DataFrame({
        'open': np.linspace(100, 110, 300),
        'high': np.linspace(100.5, 110.5, 300),
        'low': np.linspace(99.5, 109.5, 300),
        'close': np.linspace(100.1, 110.1, 300),
        'volume': [1000] * 300
    })
    
    # Forzar algunas condiciones para que los indicadores den BUY
    # EMA 200 será aprox 105, el precio actual es 110 -> Bullish
    # RSI será alto (overbought), CCI será alto, etc.
    
    all_indicators = indicator_service.calculate_all(df)
    direction, met, details = indicator_service.evaluate_signals(df, all_indicators)
    
    print(f"\n--- Simulación Escenario Alcista ---")
    print(f"Dirección Resultante: {direction}")
    print(f"Indicadores que cumplieron: {met}")
    print(f"Detalles:")
    for d in details:
        print(f"  - {d}")
        
    # Calcular el score manual para verificar
    buy_score = 0
    for d in details:
        if "Buy" in d or "Bullish" in d or "Above" in d:
            # Buscar el peso en DEFAULT_INDICATORS
            for ind in DEFAULT_INDICATORS:
                if ind.name in d.upper() or (ind.name == "EMA_200" and "EMA200" in d):
                    buy_score += ind.weight
                    break
    
    print(f"\nScore de Compra Calculado: {buy_score:.2f}")
    if buy_score < min_score:
        print(f"¡ALERTA! El score ({buy_score:.2f}) es MENOR que el umbral ({min_score:.2f}).")
        print("La señal se descarta silenciosamente como NEUTRAL.")

if __name__ == "__main__":
    asyncio.run(audit())
