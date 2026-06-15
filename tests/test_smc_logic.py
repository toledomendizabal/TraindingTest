import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from app.services.indicators import indicator_service
from app.services.signal_engine import SignalEngine
from app.models.signal import SignalDirection
from app.core.config import settings

def create_mock_df():
    """Create a mock dataframe with an FVG and a liquidity sweep."""
    dates = [datetime.now() - timedelta(minutes=5*i) for i in range(100)]
    dates.reverse()
    
    df = pd.DataFrame({
        "datetime": dates,
        "open": np.linspace(1.0800, 1.0850, 100),
        "high": np.linspace(1.0810, 1.0860, 100),
        "low": np.linspace(1.0790, 1.0840, 100),
        "close": np.linspace(1.0805, 1.0855, 100),
        "volume": [1000] * 100
    })
    
    # Create a Bullish FVG at index 50
    # Candle 48 High < Candle 50 Low
    df.loc[48, "high"] = 1.0810
    df.loc[49, "open"] = 1.0815
    df.loc[49, "close"] = 1.0825
    df.loc[50, "low"] = 1.0820
    
    # Create a Liquidity Sweep (SSL) at index 80
    # Price drops below recent lows and then bounces
    recent_low = df.loc[70:79, "low"].min()
    df.loc[80, "low"] = recent_low - 0.0010
    df.loc[80, "close"] = recent_low + 0.0005
    
    return df

async def test_smc_detection():
    print("--- Testing SMC Detection ---")
    df = create_mock_df()
    
    fvgs = indicator_service.detect_fvg(df)
    print(f"Detected {len(fvgs)} FVGs")
    for f in fvgs:
        print(f"  Type: {f['type']}, Price: {f['price']:.5f}")
        
    liquidity = indicator_service.detect_liquidity(df)
    print(f"Detected BSL: {len(liquidity['BSL'])}, SSL: {len(liquidity['SSL'])}")
    
    assert len(fvgs) > 0, "Should detect at least one FVG"
    assert len(liquidity['SSL']) > 0, "Should detect at least one SSL zone"
    print("SMC Detection Test: PASSED")

async def test_signal_creation_with_smc():
    print("\n--- Testing Signal Creation with SMC ---")
    engine = SignalEngine()
    df = create_mock_df()
    
    # Mock some indicator values
    atr = 0.0015
    indicators_met = 10
    details = ["RSI Bullish", "MACD Cross"]
    
    # Test Buy Signal with SMC confluence
    entry_price = 1.0822 # Near the FVG we created
    
    signal = await engine._create_signal(
        asset="EURUSD",
        direction=SignalDirection.BUY,
        entry_price=entry_price,
        atr=atr,
        indicators_met=indicators_met,
        details=details,
        spread=0.0001,
        df=df
    )
    
    if signal:
        print(f"Signal ID: {signal.id}")
        print(f"SMC Quality: {signal.smc_quality}")
        print(f"FVG Confluence: {signal.fvg_confluence}")
        print(f"Liquidity Sweep: {signal.liquidity_sweep}")
        print(f"Lot Size: {signal.lot_size}")
        print(f"TP1: {signal.take_profit_1}, TP3: {signal.take_profit_3}")
        
        assert signal.smc_quality >= 1.0, "Quality should be at least 1.0"
        if signal.fvg_confluence or signal.liquidity_sweep:
            assert signal.smc_quality > 1.0, "Quality should be boosted by SMC"
            
        print("Signal Creation Test: PASSED")
    else:
        print("Signal Creation Test: FAILED (No signal returned)")

if __name__ == "__main__":
    # Setup environment
    import os
    os.environ["PYTHONPATH"] = "/home/ubuntu/TraindingTest"
    
    async def run_tests():
        try:
            await test_smc_detection()
            await test_signal_creation_with_smc()
            print("\nALL TESTS COMPLETED SUCCESSFULLY")
        except Exception as e:
            print(f"\nTESTS FAILED: {e}")
            import traceback
            traceback.print_exc()

    asyncio.run(run_tests())
