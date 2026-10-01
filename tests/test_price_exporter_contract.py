"""
Contrato PriceExporter.mq5 (v2.2) <-> backend (market_data.py).

No se puede compilar MQL5 fuera de MetaEditor, así que se verifica:
  1) estáticamente que el .mq5 contiene las piezas clave, y
  2) que, simulando los nombres de archivo que el EA escribe para cada símbolo
     del mt4_prices.csv real del bróker (sufijo "..."), el backend resuelve
     precio e historial (base/30m/1h/4h/1d) de todos los activos con alias.
"""
import asyncio
import csv
import re
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.core.config import settings
from app.services.market_data import MarketDataService

ROOT = Path(__file__).resolve().parent.parent
MQ5 = (ROOT / "scripts" / "PriceExporter.mq5").read_text(encoding="utf-8")
FIXTURE = Path(__file__).parent / "fixtures" / "mt4_prices_mexatlantic.csv"
SUFFIX = "..."


def ea_safe_symbol(sym: str) -> str:
    """Réplica de SafeFileSymbol() del EA."""
    for ch in '/\\:*?"<>|':
        sym = sym.replace(ch, "")
    return sym


def ea_files(sym: str, daily=True, m5=False):
    s = ea_safe_symbol(sym)
    names = [f"history_{s}.csv", f"history_{s}_30m.csv", f"history_{s}_1h.csv", f"history_{s}_4h.csv"]
    if daily:
        names.append(f"history_{s}_1d.csv")
    if m5:
        names.append(f"history_{s}_5m.csv")
    return names


def _df(base, n=80):
    close = base + np.linspace(0, base * 0.001, n)
    return pd.DataFrame({
        "datetime": pd.date_range("2026-09-01", periods=n, freq="1h").strftime("%Y-%m-%d %H:%M:%S"),
        "open": close, "high": close * 1.0003, "low": close * 0.9997, "close": close, "volume": 10,
    })


class TestStaticEA:
    def test_version_and_suffix_inputs(self):
        assert '#property version   "2.20"' in MQ5
        assert re.search(r'input string SymbolSuffix = "\.\.\."', MQ5)
        assert "input bool   AutoSelectSuffixSymbols = true" in MQ5
        assert "SymbolsTotal(false)" in MQ5          # recorre TODOS los símbolos del servidor
        assert "HasSuffix(name, SymbolSuffix)" in MQ5

    def test_all_timeframes_exported(self):
        for tf, suf in [("PERIOD_M1", '""'), ("PERIOD_M30", '"_30m"'), ("PERIOD_H1", '"_1h"'),
                        ("PERIOD_H4", '"_4h"'), ("PERIOD_D1", '"_1d"')]:
            assert re.search(rf"ExportHistoryFile\(symbol, safe_symbol, {tf},\s*{re.escape(suf)}\)", MQ5), tf

    def test_no_silent_skip_and_no_empty_files(self):
        assert "if(!SymbolIsSynchronized(symbol)) continue;" not in MQ5
        assert "if(copied <= 0) return(false);" in MQ5
        assert MQ5.index("CopyRates(symbol, period") < MQ5.index("FileOpen(fileName")

    def test_uses_timelocal_for_history_timer(self):
        assert "datetime now = TimeLocal();" in MQ5

    def test_braces_balanced(self):
        code = re.sub(r'"(\\.|[^"\\\n])*"', '""', MQ5)
        code = re.sub(r"//[^\n]*", "", code)
        for a, b in ("{}", "()", "[]"):
            assert code.count(a) == code.count(b)


class TestEAFilesResolvedByBackend:
    def test_all_suffix_symbols_resolve_in_backend(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "MT4_FILES_PATH", str(tmp_path))
        monkeypatch.setattr(settings, "TWELVE_DATA_ENABLED", False)
        shutil.copy(FIXTURE, tmp_path / "mt4_prices.csv")

        with open(FIXTURE, newline="", encoding="utf-8") as f:
            rows = {r["Symbol"].strip(): float(r["Bid"]) for r in csv.DictReader(f)}

        # El EA generaría archivos para cada símbolo exportado (con y sin sufijo)
        for sym, bid in rows.items():
            for i, name in enumerate(ea_files(sym)):
                _df(bid * (1 + i * 0.001)).to_csv(tmp_path / name, index=False)

        # Sufijo con puntos: nombre de archivo válido y esperado
        assert (tmp_path / "history_EURUSD....csv").exists()
        assert (tmp_path / "history_EURUSD..._1d.csv").exists()

        svc = MarketDataService()
        suffixed = [s for s in rows if s.endswith(SUFFIX)]
        assert len(suffixed) >= 20
        failures = []
        for asset, alias in settings.MT_SYMBOL_ALIASES.items():
            for tf in ("5m", "30m", "1h", "4h", "1d"):
                df = asyncio.run(svc.get_time_series(asset, tf))
                if df is None or df.empty:
                    failures.append((asset, tf))
        assert not failures, failures

    def test_daily_file_is_used_for_1d_not_m1(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "MT4_FILES_PATH", str(tmp_path))
        monkeypatch.setattr(settings, "TWELVE_DATA_ENABLED", False)
        _df(1.10).to_csv(tmp_path / "history_EURUSD....csv", index=False)       # M1
        _df(1.50).to_csv(tmp_path / "history_EURUSD..._1d.csv", index=False)    # D1
        svc = MarketDataService()
        d1 = asyncio.run(svc.get_time_series("EURUSD", "1d"))
        m1 = asyncio.run(svc.get_time_series("EURUSD", "5m"))
        assert d1["close"].iloc[0] > 1.4 and m1["close"].iloc[0] < 1.2

    def test_m5_file_used_when_exporter_writes_it(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "MT4_FILES_PATH", str(tmp_path))
        monkeypatch.setattr(settings, "TWELVE_DATA_ENABLED", False)
        _df(1.10).to_csv(tmp_path / "history_EURUSD....csv", index=False)
        _df(1.25).to_csv(tmp_path / "history_EURUSD..._5m.csv", index=False)
        df = asyncio.run(MarketDataService().get_time_series("EURUSD", "5m"))
        assert df["close"].iloc[0] > 1.2

    @pytest.mark.parametrize("raw,expected", [
        ("EURUSD...", "EURUSD..."), ("US30", "US30"), ("NDAQ.OQ", "NDAQ.OQ"),
        ("EUR/USD...", "EURUSD..."), ('A:B*C?D"E<F>G|H', "ABCDEFGH"),
    ])
    def test_safe_symbol_matches_ea_logic(self, raw, expected):
        assert ea_safe_symbol(raw) == expected
