"""Comprehensive test suite for TradingSignal Pro system."""
import os
import sys
import asyncio
import pytest
import pandas as pd
import numpy as np
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestConfiguration:
    """Test configuration module."""

    def test_settings_load(self):
        """Test that settings load correctly."""
        from app.core.config import settings
        assert settings.INITIAL_CAPITAL == 10000.0
        assert settings.RISK_PERCENTAGE == 0.3
        assert settings.API_PORT == 8000
        assert len(settings.ACTIVE_ASSETS) == 12

    def test_active_assets_valid(self):
        """Test that all active assets are valid."""
        from app.core.config import settings
        expected_assets = [
            "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
            "USDCAD", "NZDUSD", "AUDUSD", "XAUUSD",
            "US30Cash", "US100Cash", "US500Cash", "GER40Cash"
        ]
        assert settings.ACTIVE_ASSETS == expected_assets

    def test_directories_configuration(self):
        """Test directory paths are set."""
        from app.core.config import settings
        assert settings.EXCEL_DIR != ""
        assert settings.LOGS_DIR != ""
        assert settings.REPORTS_DIR != ""


class TestModels:
    """Test data models."""

    def test_signal_model(self):
        """Test Signal model creation."""
        from app.models.signal import Signal, SignalDirection, SignalStatus

        signal = Signal(
            id="test001",
            asset="EURUSD",
            direction=SignalDirection.BUY,
            entry_price=1.08432,
            stop_loss=1.08130,
            take_profit_1=1.08733,
            take_profit_2=1.09034,
            take_profit_3=1.09432,
            sl_pips=30.2,
            tp1_pips=30.1,
            tp2_pips=60.2,
            tp3_pips=100.0,
            lot_size=0.10,
            indicators_met=12,
            score=66.7,
            status=SignalStatus.ACTIVE,
            created_at=datetime.now()
        )

        assert signal.asset == "EURUSD"
        assert signal.direction == SignalDirection.BUY
        assert signal.status == SignalStatus.ACTIVE
        assert signal.lot_size == 0.10

    def test_asset_pip_info(self):
        """Test asset pip information."""
        from app.models.asset import Asset

        # Standard forex
        info = Asset.get_pip_info("EURUSD")
        assert info["pip_value"] == 0.0001
        assert info["contract_size"] == 100000.0

        # JPY pair
        info = Asset.get_pip_info("USDJPY")
        assert info["pip_value"] == 0.01

        # Gold
        info = Asset.get_pip_info("XAUUSD")
        assert info["pip_value"] == 0.01
        assert info["contract_size"] == 100.0

        # Index
        info = Asset.get_pip_info("US30Cash")
        assert info["pip_value"] == 1.0
        assert info["contract_size"] == 1.0

    def test_indicator_config(self):
        """Test indicator configuration."""
        from app.models.indicator import get_default_indicators

        indicators = get_default_indicators()
        assert len(indicators) == 18

        # Check categories
        categories = set(i.category for i in indicators)
        assert "trend" in categories
        assert "momentum" in categories
        assert "volatility" in categories
        assert "volume" in categories


class TestIndicators:
    """Test technical indicator calculations."""

    def _create_sample_df(self, n=250):
        """Create sample OHLCV dataframe."""
        np.random.seed(42)
        dates = pd.date_range(start="2024-01-01", periods=n, freq="5min")
        close = 1.08 + np.cumsum(np.random.randn(n) * 0.0001)
        high = close + np.abs(np.random.randn(n) * 0.0005)
        low = close - np.abs(np.random.randn(n) * 0.0005)
        open_price = close + np.random.randn(n) * 0.0002
        volume = np.random.randint(100, 10000, n)

        return pd.DataFrame({
            "datetime": dates,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume
        })

    def test_ema_calculation(self):
        """Test EMA calculation."""
        from app.services.indicators import indicator_service

        df = self._create_sample_df()
        result = indicator_service._calc_ema(df, 200)
        assert result is not None
        assert isinstance(result, float)

    def test_rsi_calculation(self):
        """Test RSI calculation."""
        from app.services.indicators import indicator_service

        df = self._create_sample_df()
        result = indicator_service._calc_rsi(df)
        assert result is not None
        assert 0 <= result <= 100

    def test_macd_calculation(self):
        """Test MACD calculation."""
        from app.services.indicators import indicator_service

        df = self._create_sample_df()
        result = indicator_service._calc_macd(df)
        assert result is not None
        assert "macd" in result
        assert "signal" in result
        assert "histogram" in result

    def test_bollinger_bands(self):
        """Test Bollinger Bands calculation."""
        from app.services.indicators import indicator_service

        df = self._create_sample_df()
        result = indicator_service._calc_bollinger(df)
        assert result is not None
        assert result["upper"] > result["middle"] > result["lower"]

    def test_atr_calculation(self):
        """Test ATR calculation."""
        from app.services.indicators import indicator_service

        df = self._create_sample_df()
        result = indicator_service._calc_atr(df)
        assert result is not None
        assert result > 0

    def test_adx_calculation(self):
        """Test ADX/DMI calculation."""
        from app.services.indicators import indicator_service

        df = self._create_sample_df()
        result = indicator_service._calc_adx(df)
        assert result is not None
        assert "adx" in result
        assert "plus_di" in result
        assert "minus_di" in result

    def test_stochastic_calculation(self):
        """Test Stochastic calculation."""
        from app.services.indicators import indicator_service

        df = self._create_sample_df()
        result = indicator_service._calc_stochastic(df)
        assert result is not None
        assert "k" in result
        assert "d" in result

    def test_ichimoku_calculation(self):
        """Test Ichimoku calculation."""
        from app.services.indicators import indicator_service

        df = self._create_sample_df()
        result = indicator_service._calc_ichimoku(df)
        assert result is not None
        assert "signal" in result

    def test_all_indicators(self):
        """Test calculating all indicators at once."""
        from app.services.indicators import indicator_service

        df = self._create_sample_df()
        results = indicator_service.calculate_all(df)
        assert len(results) > 0
        assert "EMA_200" in results
        assert "RSI" in results
        assert "MACD" in results

    def test_signal_evaluation(self):
        """Test signal evaluation logic."""
        from app.services.indicators import indicator_service

        df = self._create_sample_df()
        indicators = indicator_service.calculate_all(df)
        direction, count, details = indicator_service.evaluate_signals(df, indicators)

        assert direction in ["BUY", "SELL", "NEUTRAL"]
        assert count >= 0
        assert isinstance(details, list)


class TestRiskManagement:
    """Test risk management calculations."""

    def test_lot_size_calculation(self):
        """Test lot size calculation."""
        from app.utils.helpers import calculate_lot_size

        # Standard forex: $10,000 capital, 0.3% risk, 30 pips SL
        lot_size = calculate_lot_size(
            capital=10000,
            risk_pct=0.3,
            sl_pips=30,
            pip_value=0.0001,
            contract_size=100000
        )

        # Risk amount = $30, pip value per lot = $10
        # Lot size = $30 / (30 * $10) = 0.10
        assert lot_size == 0.10

    def test_lot_size_gold(self):
        """Test lot size for gold."""
        from app.utils.helpers import calculate_lot_size

        lot_size = calculate_lot_size(
            capital=10000,
            risk_pct=0.3,
            sl_pips=300,  # 3.00 in gold = 300 pips
            pip_value=0.01,
            contract_size=100
        )
        assert lot_size >= 0.01
        assert lot_size <= 10.0

    def test_pip_calculation(self):
        """Test pip distance calculation."""
        from app.utils.helpers import calculate_pips

        pips = calculate_pips(1.08432, 1.08132, 0.0001)
        assert abs(pips - 30.0) < 0.1


class TestExcelManager:
    """Test Excel manager functionality."""

    def test_file_creation(self):
        """Test Excel files are created."""
        from app.services.excel_manager import excel_manager

        assert os.path.exists(excel_manager.signals_file)
        assert os.path.exists(excel_manager.config_file)

    def test_config_read(self):
        """Test reading configuration from Excel."""
        from app.services.excel_manager import excel_manager

        config = excel_manager.get_config()
        assert "assets" in config
        assert "parameters" in config
        assert "indicators" in config

    def test_statistics(self):
        """Test statistics calculation."""
        from app.services.excel_manager import excel_manager

        stats = excel_manager.get_statistics()
        assert "total_signals" in stats
        assert "win_rate" in stats
        assert "profit_factor" in stats


class TestMarketData:
    """Test market data service."""

    def test_symbol_mapping(self):
        """Test symbol mapping for Twelve Data."""
        from app.services.market_data import market_data_service

        assert market_data_service._get_symbol("EURUSD") == "EUR/USD"
        assert market_data_service._get_symbol("XAUUSD") == "XAU/USD"
        assert market_data_service._get_symbol("US30Cash") == "DJI"

    def test_session_detection(self):
        """Test trading session detection."""
        from app.services.market_data import market_data_service

        session = market_data_service.get_current_session()
        assert session in ["Tokyo", "London", "NewYork"]


class TestBacktesting:
    """Test backtesting service."""

    def test_empty_analysis(self):
        """Test backtesting with no signals."""
        from app.services.backtesting import backtesting_service

        result = backtesting_service._analyze_signals([], "2024-01-01")
        assert result.total_signals == 0
        assert len(result.recommendations) > 0

    def test_winning_analysis(self):
        """Test backtesting with winning signals."""
        from app.services.backtesting import backtesting_service

        signals = [
            {"profit_loss": 30.0, "status": "CLOSED_TP1"},
            {"profit_loss": 60.0, "status": "CLOSED_TP2"},
            {"profit_loss": -30.0, "status": "CLOSED_SL"},
        ]

        result = backtesting_service._analyze_signals(signals, "2024-01-01")
        assert result.total_signals == 3
        assert result.winning_signals == 2
        assert result.losing_signals == 1
        assert result.win_rate == pytest.approx(66.67, abs=0.1)

    def test_report_format(self):
        """Test report formatting."""
        from app.services.backtesting import backtesting_service
        from app.models.signal import BacktestResult

        result = BacktestResult(
            date="2024-01-01",
            total_signals=10,
            winning_signals=7,
            losing_signals=3,
            win_rate=70.0,
            profit_factor=2.3,
            max_drawdown=5.0,
            sharpe_ratio=1.5,
            total_profit=210.0,
            total_loss=90.0,
            net_profit=120.0,
            recommendations=["Test recommendation"],
            indicator_adjustments=["Test adjustment"]
        )

        content = backtesting_service._format_report(result, "daily")
        assert "BACKTESTING" in content
        assert "70.0%" in content


class TestAPIEndpoints:
    """Test API endpoint responses."""

    def test_app_creation(self):
        """Test FastAPI app is created correctly."""
        from app.main import app
        assert app.title == "TradingSignal Pro"

    def test_routes_registered(self):
        """Test that all routes are registered."""
        from app.main import app

        routes = [route.path for route in app.routes]
        assert "/api/signals/active" in routes or any("/signals" in r for r in routes)


def run_all_tests():
    """Run all tests and print results."""
    print("=" * 60)
    print("TradingSignal Pro - Test Suite")
    print("=" * 60)
    print()

    test_classes = [
        TestConfiguration,
        TestModels,
        TestIndicators,
        TestRiskManagement,
        TestExcelManager,
        TestMarketData,
        TestBacktesting,
        TestAPIEndpoints,
    ]

    total_tests = 0
    passed_tests = 0
    failed_tests = 0
    errors = []

    for test_class in test_classes:
        instance = test_class()
        class_name = test_class.__name__
        print(f"\n--- {class_name} ---")

        methods = [m for m in dir(instance) if m.startswith("test_")]
        for method_name in methods:
            total_tests += 1
            try:
                method = getattr(instance, method_name)
                method()
                passed_tests += 1
                print(f"  ✓ {method_name}")
            except Exception as e:
                failed_tests += 1
                errors.append(f"{class_name}.{method_name}: {str(e)}")
                print(f"  ✗ {method_name}: {str(e)[:80]}")

    print("\n" + "=" * 60)
    print(f"RESULTADOS: {passed_tests}/{total_tests} pasaron, {failed_tests} fallaron")
    print("=" * 60)

    if errors:
        print("\nErrores detallados:")
        for err in errors:
            print(f"  - {err}")

    return failed_tests == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
