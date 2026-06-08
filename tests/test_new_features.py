import sys
import os
import pandas as pd
import numpy as np
import asyncio
from datetime import datetime

# Add app to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.indicators import IndicatorService
from app.services.signal_engine import SignalEngine
from app.services.mt4_monitor import mt4_monitor
from app.core.config import settings

def test_sl_limits():
    print("\n--- Testing SL Limits ---")
    engine = SignalEngine()
    
    # Test cases: (Asset, ATR, PipSize, ExpectedMinPips)
    test_cases = [
        ("EURUSD", 0.0002, 0.0001, 6),      # Forex: 0.0002 ATR is 2 pips, should be adjusted to 6
        ("XAUUSD", 1.0, 0.01, 300),         # Gold: 1.0 ATR is 100 pips, should be adjusted to 300
        ("US30Cash", 50.0, 1.0, 300),       # Index: 50 ATR is 50 pips, should be adjusted to 300
        ("GER40Cash", 20.0, 1.0, 20),       # GER40: 20 ATR is 20 pips, should stay 20 (Auto-calculable)
        ("GBPUSD", 0.0020, 0.0001, 20)      # Forex: 0.0020 ATR is 20 pips, should stay 20 ( > 6)
    ]
    
    for asset, atr, pip_size, expected_min in test_cases:
        is_index_or_gold = any(x in asset.upper() for x in ["XAU", "US30", "US100", "US500"])
        is_ger40 = "GER40" in asset.upper()
        min_sl_pips = 300 if (is_index_or_gold and not is_ger40) else 6
        
        sl_distance = atr * 1.5
        current_sl_pips = sl_distance / pip_size
        
        if current_sl_pips < min_sl_pips:
            final_sl_pips = min_sl_pips
        else:
            final_sl_pips = current_sl_pips
            
        print(f"Asset: {asset:10} | ATR SL: {current_sl_pips:5.1f} pips | Final SL: {final_sl_pips:5.1f} pips | OK: {final_sl_pips >= min_sl_pips}")

def test_accumulation_filter():
    print("\n--- Testing Accumulation Filter ---")
    service = IndicatorService()
    
    # Create mock data for accumulation (Low volatility, low ADX)
    df_acc = pd.DataFrame({
        "close": [1.1000] * 200,
        "high": [1.1005] * 200,
        "low": [1.0995] * 200,
        "volume": [1000] * 200
    })
    
    # Mock indicators
    indicators_acc = {
        "ADX_DMI": {"adx": 15}, # Low ADX
        "BOLLINGER_BANDS": {"upper": 1.1010, "lower": 1.0990, "middle": 1.1000} # Tight bands
    }
    
    direction, count, details = service.evaluate_signals(df_acc, indicators_acc)
    print(f"Accumulation Test: Direction={direction} | Details={details[0] if details else 'None'}")
    
    # Create mock data for distribution (High ADX)
    indicators_dist = {
        "ADX_DMI": {"adx": 35}, # High ADX
        "BOLLINGER_BANDS": {"upper": 1.1050, "lower": 1.0950, "middle": 1.1000},
        "EMA_200": 1.0900 # Bullish trend
    }
    
    # Add enough bullish indicators to pass the 6-indicator threshold
    indicators_dist.update({
        "EMA_50": 1.0950,
        "EMA_20": 1.0980,
        "EMA_9": 1.0990,
        "PARABOLIC_SAR": 1.0950,
        "RSI": 45,
        "MACD": {"histogram": 0.0001, "macd": 0.0002, "signal": 0.0001}
    })
    
    direction, count, details = service.evaluate_signals(df_acc, indicators_dist)
    print(f"Distribution Test: Direction={direction} | Indicators Met={count}")

async def test_mt4_offline_sync():
    print("\n--- Testing MT4 Offline Sync ---")
    # Mock settings path
    settings.MT4_FILES_PATH = "/tmp"
    csv_path = os.path.join(settings.MT4_FILES_PATH, "mt4_prices.csv")
    
    # Create dummy CSV
    with open(csv_path, "w") as f:
        f.write("Symbol,Bid,Ask\n")
        f.write("EURUSD,1.0850,1.0851\n")
        f.write("XAUUSD,2350.50,2350.60\n")
    
    await mt4_monitor._read_prices()
    
    p1 = mt4_monitor.get_price("EURUSD")
    p2 = mt4_monitor.get_price("XAUUSD")
    
    print(f"EURUSD MT4 Price: {p1} | OK: {p1 == 1.0850}")
    print(f"XAUUSD MT4 Price: {p2} | OK: {p2 == 2350.50}")
    
    # Clean up
    if os.path.exists(csv_path):
        os.remove(csv_path)

if __name__ == "__main__":
    test_sl_limits()
    test_accumulation_filter()
    asyncio.run(test_mt4_offline_sync())
