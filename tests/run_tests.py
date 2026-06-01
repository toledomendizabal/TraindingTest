"""Run all validation tests for TradingSignal Pro."""
import sys
import os
import numpy as np
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

passed = 0
failed = 0
errors = []


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        errors.append(f"{name}: {detail}")
        print(f"  ✗ {name} - {detail}")


def create_sample_df(n=250):
    """Create sample OHLCV dataframe."""
    np.random.seed(42)
    dates = pd.date_range(start="2024-01-01", periods=n, freq="5min")
    close = 1.08 + np.cumsum(np.random.randn(n) * 0.0001)
    high = close + np.abs(np.random.randn(n) * 0.0005)
    low = close - np.abs(np.random.randn(n) * 0.0005)
    open_price = close + np.random.randn(n) * 0.0002
    volume = np.random.randint(100, 10000, n).astype(float)
    return pd.DataFrame({
        "datetime": dates,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume
    })


print("=" * 60)
print("TradingSignal Pro - Validación Completa del Sistema")
print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)

# === Module 1: Configuration ===
print("\n[1] CONFIGURACIÓN")
try:
    from app.core.config import settings
    test("Settings carga correctamente", True)
    test("Capital inicial = $10,000", settings.INITIAL_CAPITAL == 10000.0)
    test("Riesgo = 0.3%", settings.RISK_PERCENTAGE == 0.3)
    test("12 activos configurados", len(settings.ACTIVE_ASSETS) == 12)
    test("Puerto API = 8000", settings.API_PORT == 8000)
except Exception as e:
    test("Módulo de configuración", False, str(e))

# === Module 2: Models ===
print("\n[2] MODELOS DE DATOS")
try:
    from app.models.signal import Signal, SignalDirection, SignalStatus, BacktestResult
    from app.models.asset import Asset, ASSET_CATALOG
    from app.models.indicator import get_default_indicators, IndicatorConfig

    signal = Signal(
        id="V001", asset="EURUSD", direction=SignalDirection.BUY,
        entry_price=1.08432, stop_loss=1.08130,
        take_profit_1=1.08733, take_profit_2=1.09034, take_profit_3=1.09432,
        sl_pips=30.2, tp1_pips=30.1, tp2_pips=60.2, tp3_pips=100.0,
        lot_size=0.10, indicators_met=12, score=66.7,
        status=SignalStatus.ACTIVE, created_at=datetime.now()
    )
    test("Signal model creación", signal.asset == "EURUSD")
    test("Signal direction BUY", signal.direction == SignalDirection.BUY)
    test("Signal status ACTIVE", signal.status == SignalStatus.ACTIVE)

    test("Asset EURUSD pip=0.0001", Asset.get_pip_info("EURUSD")["pip_value"] == 0.0001)
    test("Asset USDJPY pip=0.01", Asset.get_pip_info("USDJPY")["pip_value"] == 0.01)
    test("Asset XAUUSD pip=0.01", Asset.get_pip_info("XAUUSD")["pip_value"] == 0.01)
    test("Asset US30Cash pip=1.0", Asset.get_pip_info("US30Cash")["pip_value"] == 1.0)
    test("Asset catalog tiene 12+ activos", len(ASSET_CATALOG) >= 12)

    indicators = get_default_indicators()
    test("18 indicadores configurados", len(indicators) == 18)
    categories = set(i.category for i in indicators)
    test("Categoría trend existe", "trend" in categories)
    test("Categoría momentum existe", "momentum" in categories)
    test("Categoría volatility existe", "volatility" in categories)
    test("Categoría volume existe", "volume" in categories)

except Exception as e:
    test("Módulo de modelos", False, str(e))

# === Module 3: Indicators ===
print("\n[3] INDICADORES TÉCNICOS")
try:
    from app.services.indicators import indicator_service

    df = create_sample_df()

    ema = indicator_service._calc_ema(df, 200)
    test("EMA 200 calculado", ema is not None and isinstance(ema, float))

    rsi = indicator_service._calc_rsi(df)
    test("RSI calculado (0-100)", rsi is not None and 0 <= rsi <= 100)

    macd = indicator_service._calc_macd(df)
    test("MACD calculado", macd is not None and "macd" in macd)

    bb = indicator_service._calc_bollinger(df)
    test("Bollinger Bands", bb is not None and bb["upper"] > bb["lower"])

    atr = indicator_service._calc_atr(df)
    test("ATR calculado (>0)", atr is not None and atr > 0)

    adx = indicator_service._calc_adx(df)
    test("ADX/DMI calculado", adx is not None and "adx" in adx)

    stoch = indicator_service._calc_stochastic(df)
    test("Stochastic calculado", stoch is not None and "k" in stoch)

    ichimoku = indicator_service._calc_ichimoku(df)
    test("Ichimoku calculado", ichimoku is not None and "signal" in ichimoku)

    all_ind = indicator_service.calculate_all(df)
    test("Todos los indicadores calculados", len(all_ind) >= 10)

    direction, count, details = indicator_service.evaluate_signals(df, all_ind)
    test("Evaluación de señales", direction in ["BUY", "SELL", "NEUTRAL"])
    test("Conteo de indicadores", count >= 0)

except Exception as e:
    test("Módulo de indicadores", False, str(e))

# === Module 4: Risk Management ===
print("\n[4] GESTIÓN DE RIESGO")
try:
    from app.utils.helpers import calculate_lot_size, calculate_pips

    # Forex standard
    lot = calculate_lot_size(10000, 0.3, 30, 0.0001, 100000)
    test("Lot size EURUSD (30 pips) = 0.10", lot == 0.10)

    # Gold
    lot_gold = calculate_lot_size(10000, 0.3, 300, 0.01, 100)
    test("Lot size XAUUSD válido", 0.01 <= lot_gold <= 10.0)

    # Pip calculation
    pips = calculate_pips(1.08432, 1.08132, 0.0001)
    test("Cálculo de pips = 30", abs(pips - 30.0) < 0.1)

    # Edge cases
    lot_min = calculate_lot_size(1000, 0.1, 100, 0.0001, 100000)
    test("Lot mínimo >= 0.01", lot_min >= 0.01)

except Exception as e:
    test("Módulo de riesgo", False, str(e))

# === Module 5: Excel Manager ===
print("\n[5] GESTOR EXCEL")
try:
    from app.services.excel_manager import excel_manager

    test("Archivo signals existe", os.path.exists(excel_manager.signals_file))
    test("Archivo config existe", os.path.exists(excel_manager.config_file))

    config = excel_manager.get_config()
    test("Config tiene assets", "assets" in config)
    test("Config tiene parameters", "parameters" in config)
    test("Config tiene indicators", "indicators" in config)

    stats = excel_manager.get_statistics()
    test("Statistics tiene win_rate", "win_rate" in stats)
    test("Statistics tiene total_signals", "total_signals" in stats)

except Exception as e:
    test("Módulo Excel", False, str(e))

# === Module 6: Market Data ===
print("\n[6] DATOS DE MERCADO")
try:
    from app.services.market_data import market_data_service

    test("Symbol EUR/USD", market_data_service._get_symbol("EURUSD") == "EUR/USD")
    test("Symbol XAU/USD", market_data_service._get_symbol("XAUUSD") == "XAU/USD")
    test("Symbol US30 = DJI", market_data_service._get_symbol("US30Cash") == "DJI")

    session = market_data_service.get_current_session()
    test("Sesión válida", session in ["Tokyo", "London", "NewYork"])

except Exception as e:
    test("Módulo Market Data", False, str(e))

# === Module 7: Signal Engine ===
print("\n[7] MOTOR DE SEÑALES")
try:
    from app.services.signal_engine import signal_engine
    test("Signal engine instanciado", signal_engine is not None)
    test("Min indicators = 6", signal_engine.min_indicators == 6)

except Exception as e:
    test("Motor de señales", False, str(e))

# === Module 8: Backtesting ===
print("\n[8] BACKTESTING")
try:
    from app.services.backtesting import backtesting_service

    # Empty analysis
    result = backtesting_service._analyze_signals([], "2024-01-01")
    test("Backtest vacío: 0 señales", result.total_signals == 0)

    # With signals
    signals = [
        {"profit_loss": 30.0, "status": "CLOSED_TP1"},
        {"profit_loss": 60.0, "status": "CLOSED_TP2"},
        {"profit_loss": -30.0, "status": "CLOSED_SL"},
    ]
    result = backtesting_service._analyze_signals(signals, "2024-01-01")
    test("Backtest: 3 señales", result.total_signals == 3)
    test("Backtest: 2 ganadoras", result.winning_signals == 2)
    test("Backtest: win rate ~66.7%", abs(result.win_rate - 66.67) < 0.1)
    test("Backtest: profit factor > 1", result.profit_factor > 1.0)

except Exception as e:
    test("Módulo Backtesting", False, str(e))

# === Module 9: Scheduler ===
print("\n[9] SCHEDULER")
try:
    from app.services.scheduler import scheduler_service
    test("Scheduler instanciado", scheduler_service is not None)
    test("Scheduler no activo (pre-start)", not scheduler_service._is_running)

except Exception as e:
    test("Módulo Scheduler", False, str(e))

# === Module 10: API ===
print("\n[10] API ENDPOINTS")
try:
    from app.main import app
    test("FastAPI app creada", app is not None)
    test("App title correcto", app.title == "TradingSignal Pro")

    routes = [route.path for route in app.routes]
    test("Ruta /api/signals/active", any("signals" in r for r in routes))
    test("Ruta /api/dashboard/overview", any("dashboard" in r for r in routes))
    test("Ruta /api/config/current", any("config" in r for r in routes))
    test("Ruta /api/backtesting/reports", any("backtesting" in r for r in routes))
    test("Ruta /api/auth/status", any("auth" in r for r in routes))

except Exception as e:
    test("Módulo API", False, str(e))

# === Module 11: Telegram ===
print("\n[11] TELEGRAM SERVICE")
try:
    from app.services.telegram_service import telegram_service
    test("Telegram service instanciado", telegram_service is not None)

except Exception as e:
    test("Módulo Telegram", False, str(e))

# === Module 12: Position Monitor ===
print("\n[12] MONITOR DE POSICIONES")
try:
    from app.services.position_monitor import position_monitor
    test("Position monitor instanciado", position_monitor is not None)

except Exception as e:
    test("Módulo Position Monitor", False, str(e))

# === SUMMARY ===
print("\n" + "=" * 60)
print(f"RESULTADOS FINALES: {passed} PASARON / {failed} FALLARON / {passed + failed} TOTAL")
print("=" * 60)

if errors:
    print("\nErrores:")
    for e in errors:
        print(f"  - {e}")
else:
    print("\n✓ TODOS LOS MÓDULOS VALIDADOS CORRECTAMENTE")

print("=" * 60)
sys.exit(0 if failed == 0 else 1)
