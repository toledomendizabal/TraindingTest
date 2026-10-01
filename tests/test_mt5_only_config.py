"""
Pruebas de integridad y funcionalidad -- cambios 2026-10-01:
  * alias de símbolos según el mt4_prices.csv real del bróker (sufijo "...")
  * Twelve Data desactivado (solo MT5)
  * R:R 1:2 / 1:3 / 1:5
  * ventana de sesión 01:00-22:00 UTC, domingo a viernes

Ejecutar:  python -m pytest tests/test_mt5_only_config.py -v
"""
import asyncio
import csv
import os
import shutil
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.core.config import settings
from app.services.market_data import MarketDataService

FIXTURE = Path(__file__).parent / "fixtures" / "mt4_prices_mexatlantic.csv"
ROOT = Path(__file__).resolve().parent.parent

# Activos de ACTIVE_ASSETS que el bróker NO exporta todavía (hay que agregarlos
# a Market Watch y a SymbolsToExport del EA). Si alguno aparece en el archivo
# real, esta lista debe actualizarse junto con MT_SYMBOL_ALIASES.
PENDING_ASSETS = {"US100Cash", "GER40Cash", "STOXX50Cash", "WTI", "BRENT", "COPPER"}


def _price_rows():
    with open(FIXTURE, newline="", encoding="utf-8") as f:
        return {r["Symbol"].strip().upper(): r for r in csv.DictReader(f)}


def _history_df(base: float, n: int = 60) -> pd.DataFrame:
    dt = pd.date_range("2026-10-01 00:00", periods=n, freq="5min")
    close = base + np.linspace(0, 0.001, n)
    return pd.DataFrame({
        "datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "open": close - 0.0001, "high": close + 0.0003,
        "low": close - 0.0003, "close": close, "volume": 100,
    })


@pytest.fixture
def mtdir(tmp_path, monkeypatch):
    shutil.copy(FIXTURE, tmp_path / "mt4_prices.csv")
    monkeypatch.setattr(settings, "MT4_FILES_PATH", str(tmp_path))
    monkeypatch.setattr(settings, "TWELVE_DATA_ENABLED", False)
    return tmp_path


@pytest.fixture
def svc():
    return MarketDataService()


# ----------------------------------------------------------------- INTEGRIDAD
class TestIntegrity:
    def test_every_alias_exists_in_broker_price_file(self):
        rows = _price_rows()
        missing = {k: v for k, v in settings.MT_SYMBOL_ALIASES.items() if v.upper() not in rows}
        assert not missing, f"alias que no existen en mt4_prices.csv: {missing}"

    def test_active_assets_resolved_or_known_pending(self):
        unresolved = {a for a in settings.ACTIVE_ASSETS if a not in settings.MT_SYMBOL_ALIASES}
        assert unresolved == PENDING_ASSETS

    def test_nasdaq_stock_is_not_used_as_us100(self):
        assert "NDAQ.OQ" not in {v.upper() for v in settings.MT_SYMBOL_ALIASES.values()}
        assert "US100Cash" not in settings.MT_SYMBOL_ALIASES

    def test_no_duplicate_alias_targets(self):
        vals = [v.upper() for v in settings.MT_SYMBOL_ALIASES.values()]
        assert len(vals) == len(set(vals))

    def test_rr_ratios(self):
        assert (settings.TP1_R_MULTIPLE, settings.TP2_R_MULTIPLE, settings.TP3_R_MULTIPLE) == (2.0, 3.0, 5.0)

    def test_close_percentages_sum_100(self):
        assert settings.TP1_CLOSE_PCT + settings.TP2_CLOSE_PCT + settings.TP3_CLOSE_PCT == pytest.approx(100.0)

    def test_session_settings(self):
        assert settings.SESSION_START_HOUR_UTC == 1
        assert settings.SESSION_END_HOUR_UTC == 22
        assert sorted(settings.SESSION_ALLOWED_WEEKDAYS) == [0, 1, 2, 3, 4, 6]  # sin sábado (5)

    def test_twelve_disabled_by_default(self):
        assert settings.TWELVE_DATA_ENABLED is False

    def test_labels_in_frontend_and_readme_match(self):
        jsx = (ROOT / "frontend/src/pages/SignalsPage.jsx").read_text(encoding="utf-8")
        for label in ("TP1 (1:2)", "TP2 (1:3)", "TP3 (1:5)"):
            assert label in jsx
        assert "1:2, 1:3, 1:5" in (ROOT / "README.md").read_text(encoding="utf-8")

    def test_telegram_message_uses_settings_not_hardcoded_r(self):
        src = (ROOT / "app/services/telegram_service.py").read_text(encoding="utf-8")
        assert "settings.TP1_R_MULTIPLE" in src and "(3R, cierra resto)" not in src


# --------------------------------------------------------------- FUNCIONALIDAD
class TestPricesAndHistory:
    def test_price_resolves_for_all_aliased_active_assets(self, mtdir, svc):
        rows = _price_rows()
        for asset, alias in settings.MT_SYMBOL_ALIASES.items():
            p = svc._get_mt4_price(asset)
            assert p is not None, f"{asset} no resolvió precio"
            assert p["bid"] == float(rows[alias.upper()]["Bid"])
            assert p["ask"] == float(rows[alias.upper()]["Ask"])

    def test_pending_assets_return_no_price(self, mtdir, svc):
        for asset in PENDING_ASSETS:
            assert svc._get_mt4_price(asset) is None

    def test_history_with_suffix_and_correct_timeframe(self, mtdir, svc):
        _history_df(1.1000).to_csv(mtdir / "history_EURUSD....csv", index=False)
        _history_df(1.2000).to_csv(mtdir / "history_EURUSD..._30m.csv", index=False)
        _history_df(1.3000).to_csv(mtdir / "history_EURUSD..._4h.csv", index=False)
        d5 = asyncio.run(svc.get_time_series("EURUSD", "5m"))
        d30 = asyncio.run(svc.get_time_series("EURUSD", "30m"))
        d4h = asyncio.run(svc.get_time_series("EURUSD", "4h"))
        assert 1.10 <= d5["close"].iloc[0] < 1.11
        assert 1.20 <= d30["close"].iloc[0] < 1.21
        assert 1.30 <= d4h["close"].iloc[0] < 1.31

    def test_index_history_without_cash_suffix(self, mtdir, svc):
        _history_df(50000.0).to_csv(mtdir / "history_US30.csv", index=False)
        df = asyncio.run(svc.get_time_series("US30Cash", "5m"))
        assert df is not None and df["close"].iloc[0] > 49000

    def test_prefix_fallback_never_returns_other_timeframe(self, mtdir, svc, monkeypatch):
        monkeypatch.setattr(settings, "MT_SYMBOL_ALIASES", {})
        _history_df(1.30).to_csv(mtdir / "history_EURUSD..._4h.csv", index=False)
        assert asyncio.run(svc.get_time_series("EURUSD", "30m")) is None  # antes devolvía el _4h
        _history_df(1.20).to_csv(mtdir / "history_EURUSD..._30m.csv", index=False)
        df = asyncio.run(svc.get_time_series("EURUSD", "30m"))
        assert 1.20 <= df["close"].iloc[0] < 1.21


class TestTwelveDisabled:
    def test_no_http_calls_when_disabled(self, mtdir, svc):
        async def boom():
            raise AssertionError("se intentó llamar a Twelve Data con TWELVE_DATA_ENABLED=False")
        svc.get_client = boom
        assert asyncio.run(svc.get_time_series("WTI", "5m")) is None
        assert asyncio.run(svc.get_price("WTI")) is None
        assert svc._quota_exhausted_until is None

    def test_price_still_served_from_mt5_when_disabled(self, mtdir, svc):
        p = asyncio.run(svc.get_price("EURUSD"))
        assert p and p["source"] == "MT4"


class TestSessionWindow:
    # 27-sep-2026 = domingo; 1-oct = jueves; 2-oct = viernes; 3-oct = sábado
    @pytest.mark.parametrize("ts,expected", [
        ("2026-09-27 00:59", False), ("2026-09-27 01:00", True),
        ("2026-09-28 12:00", True),  ("2026-10-01 00:59", False),
        ("2026-10-01 21:59", True),  ("2026-10-01 22:00", False),
        ("2026-10-02 21:59", True),  ("2026-10-02 22:00", False),
        ("2026-10-03 12:00", False), ("2026-10-03 01:30", False),
    ])
    def test_window(self, svc, ts, expected):
        assert svc.is_trading_window_open(datetime.fromisoformat(ts)) is expected

    def test_filter_disabled_always_open(self, svc, monkeypatch):
        monkeypatch.setattr(settings, "SESSION_FILTER_ENABLED", False)
        assert svc.is_trading_window_open(datetime(2026, 10, 3, 12, 0)) is True


class TestSignalRiskReward:
    @pytest.mark.parametrize("asset,direction,base", [
        ("EURUSD", "BUY", 1.1250), ("EURUSD", "SELL", 1.1250),
        ("USDJPY", "BUY", 158.0), ("XAUUSD", "SELL", 4177.0),
    ])
    def test_tp_distances_are_2_3_5_times_sl(self, asset, direction, base):
        from app.services.signal_engine import signal_engine
        n = 120
        rng = np.random.default_rng(7)
        close = base + np.cumsum(rng.normal(0, base * 0.0004, n))
        df = pd.DataFrame({
            "datetime": pd.date_range("2026-10-01", periods=n, freq="5min"),
            "open": close, "high": close + base * 0.0006,
            "low": close - base * 0.0006, "close": close, "volume": 100,
        })
        sig = signal_engine._create_signal(asset, direction, df, 1)
        assert sig is not None
        sl = abs(sig.entry_price - sig.stop_loss)
        assert abs(sig.take_profit_1 - sig.entry_price) == pytest.approx(2 * sl, rel=1e-6)
        assert abs(sig.take_profit_2 - sig.entry_price) == pytest.approx(3 * sl, rel=1e-6)
        assert abs(sig.take_profit_3 - sig.entry_price) == pytest.approx(5 * sl, rel=1e-6)
        sign = 1 if direction == "BUY" else -1
        assert sign * (sig.take_profit_1 - sig.entry_price) > 0
        assert sig.take_profit_1 != sig.take_profit_2 != sig.take_profit_3
