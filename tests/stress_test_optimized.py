
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime
from loguru import logger
from app.services.signal_engine import SignalEngine
from app.services.market_data import market_data_service
from app.models.asset import Asset

async def run_stress_test():
    engine = SignalEngine()
    asset = "EURUSD"
    
    logger.info(f"Starting stress test for {asset} with optimized parameters...")
    
    # 1. Simulate market data
    # Create a bullish trend scenario
    dates = pd.date_range(end=datetime.now(), periods=500, freq='5min')
    df = pd.DataFrame({
        'open': np.linspace(1.1000, 1.1100, 500) + np.random.normal(0, 0.0001, 500),
        'high': np.linspace(1.1005, 1.1105, 500) + np.random.normal(0, 0.0001, 500),
        'low': np.linspace(1.0995, 1.1095, 500) + np.random.normal(0, 0.0001, 500),
        'close': np.linspace(1.1002, 1.1102, 500) + np.random.normal(0, 0.0001, 500),
        'volume': np.random.randint(100, 1000, 500)
    }, index=dates)
    
    # Mock market_data_service.get_time_series
    async def mock_get_time_series(asset, interval, outputsize=200):
        return df.tail(outputsize)
    
    market_data_service.get_time_series = mock_get_time_series
    
    # Mock market_data_service.get_price
    async def mock_get_price(asset):
        return {"bid": df['close'].iloc[-1], "ask": df['close'].iloc[-1] + 0.0001}
    
    market_data_service.get_price = mock_get_price
    
    # Mock _validate_structural to return True
    async def mock_validate_structural(asset, direction):
        return True
    
    engine._validate_structural = mock_validate_structural
    
    # Run analysis
    signal = await engine.analyze_asset(asset)
    
    if signal:
        logger.info(f"SUCCESS: Signal generated!")
        logger.info(f"Direction: {signal.direction}")
        logger.info(f"Score: {signal.score}")
        logger.info(f"Indicators Met: {signal.indicators_met}")
        logger.info(f"Lot Size: {signal.lot_size}")
        logger.info(f"SL: {signal.stop_loss} ({signal.sl_pips} pips)")
        logger.info(f"TP: {signal.take_profit_1} ({signal.tp1_pips} pips)")
        
        # Verify RR ratio
        rr = signal.tp1_pips / signal.sl_pips
        logger.info(f"RR Ratio: {round(rr, 2)}")
        
        # Verify Risk
        pip_info = Asset.get_pip_info(asset)
        risk = signal.lot_size * signal.sl_pips * 10 # Simplified for FX
        logger.info(f"Estimated Risk: ${round(risk, 2)}")
    else:
        logger.warning("FAILED: No signal generated. Check filters or indicators.")

if __name__ == "__main__":
    asyncio.run(run_stress_test())
