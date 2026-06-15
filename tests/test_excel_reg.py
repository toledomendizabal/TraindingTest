import asyncio
import os
import pandas as pd
from datetime import datetime
from app.services.excel_manager import excel_manager
from app.models.signal import Signal, SignalDirection, SignalStatus

async def test_excel_registration():
    print("--- Testing Excel Registration with SMC ---")
    
    # Mock signal
    signal = Signal(
        id="TEST-SMC",
        asset="XAUUSD",
        direction=SignalDirection.BUY,
        entry_price=2350.50,
        stop_loss=2340.00,
        take_profit_1=2380.00,
        take_profit_2=2400.00,
        take_profit_3=2450.00,
        sl_pips=1050.0,
        tp1_pips=3000.0,
        tp2_pips=5000.0,
        tp3_pips=10000.0,
        lot_size=0.15,
        timeframe="5m",
        indicators_met=12,
        total_indicators=18,
        score=66.7,
        status=SignalStatus.ACTIVE,
        session="New York",
        created_at=datetime.now(),
        entry_hour="14:30",
        entry_spread=0.5,
        entry_atr=1.2,
        smc_quality=1.25,
        fvg_confluence=True,
        liquidity_sweep=True,
        indicators_detail=["RSI Bullish", "FVG Detected"]
    )
    
    success = await excel_manager.register_signal(signal)
    print(f"Registration success: {success}")
    
    if success:
        # Verify columns in Excel
        df = pd.read_excel(excel_manager.signals_file)
        print(f"Excel Columns: {df.columns.tolist()}")
        
        last_row = df.iloc[-1]
        print(f"Last Row SMC Data:")
        print(f"  smc_quality: {last_row.get('smc_quality')}")
        print(f"  fvg_confluence: {last_row.get('fvg_confluence')}")
        print(f"  liquidity_sweep: {last_row.get('liquidity_sweep')}")
        
        assert "smc_quality" in df.columns, "smc_quality column missing"
        assert last_row["smc_quality"] == 1.25, "smc_quality value mismatch"
        print("Excel Registration Test: PASSED")
    else:
        print("Excel Registration Test: FAILED")

if __name__ == "__main__":
    asyncio.run(test_excel_registration())
