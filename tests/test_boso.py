"""
Regression tests for Stock Boso rules v2.1 / engine v2.1.1.

    pip install pytest
    pytest -q

These were written to FAIL against engine v2.1 and pass after v2.1.1.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

import boso

FX = json.loads((Path(__file__).parent / "fixtures" / "bars.json").read_text())


def df_of(sym: str) -> pd.DataFrame:
    return boso.bars_to_df(FX[sym])


@pytest.fixture
def benches() -> dict:
    return {b: boso.bench_series(df_of(b)) for b in ("QQQ", "SMH")}


# ---------------------------------------------------------------------------
# 1. Benchmark returns compare matching DATES, not positions
# ---------------------------------------------------------------------------
def test_bench_alignment_missing_session(benches):
    """ACME is missing one session. Its 20-day window spans 21 calendar-trading
    days of the benchmark, so a positional lookup is off by one bar."""
    df = df_of("ACME")
    r = boso.analyze("ACME", df, benches, None, now=None)
    start = df.index[-21]
    end = df.index[-1]
    q = benches[boso.bench_for("ACME")]["close"]
    expected = (float(q.asof(end)) / float(q.asof(start)) - 1) * 100
    stock_d20 = (float(df["Close"].iloc[-1]) / float(df["Close"].iloc[-21]) - 1) * 100
    assert r["RS vs bench"] == pytest.approx(stock_d20 - expected, abs=0.01)


# ---------------------------------------------------------------------------
# 2. Flat prices: RSI and ATR handle zero movement without crashing
# ---------------------------------------------------------------------------
def test_flat_tail_no_nan(benches):
    """25 flat sessions: Wilder smoothing decays, nothing is NaN or inf, labels still resolve."""
    r = boso.analyze("FLAT", df_of("FLAT"), benches, None, now=None)
    assert r is not None
    assert r["RSI"] is not None and 0 <= r["RSI"] <= 100
    assert r["ATR %"] is not None and r["ATR %"] >= 0
    assert r["Breakout score"] is not None
    assert "Invalid data" not in r["Flags"]


def test_fully_flat_is_invalid(benches):
    """A series with no movement at all has ATR 0: distances are undefined, so the score is withheld."""
    df = df_of("FLAT").copy()
    df[["Open", "High", "Low", "Close"]] = 80.0
    r = boso.analyze("FLATX", df, benches, None, now=None)
    assert r is not None
    assert "Invalid data" in r["Flags"]
    assert r["Breakout score"] is None


# ---------------------------------------------------------------------------
# 3. Rising only: RSI reaches 100, no NaN/inf
# ---------------------------------------------------------------------------
def test_rsi_rising_only():
    """30 straight up days: RSI is very high and finite (Wilder decays old losses, it doesn't forget them).
    A series that only ever rises hits exactly 100 with no division error."""
    v = boso.rsi_wilder(df_of("UPUP")["Close"])
    assert 85 < v <= 100 and v == v
    only_up = pd.Series([100 * 1.002 ** i for i in range(60)])
    assert boso.rsi_wilder(only_up) == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# 4. RSI/ATR seeding matches the SMA-seeded reference (TradingView RMA)
# ---------------------------------------------------------------------------
def rma_reference_rsi(close: list[float], n: int = 14) -> float:
    g = l = 0.0
    for i in range(1, n + 1):
        d = close[i] - close[i - 1]
        g += max(d, 0); l += max(-d, 0)
    g /= n; l /= n
    for i in range(n + 1, len(close)):
        d = close[i] - close[i - 1]
        g = (g * (n - 1) + max(d, 0)) / n
        l = (l * (n - 1) + max(-d, 0)) / n
    return 100.0 if l == 0 else 100 - 100 / (1 + g / l)


def test_rsi_seeded_like_reference():
    close = df_of("ACME")["Close"]
    assert boso.rsi_wilder(close) == pytest.approx(rma_reference_rsi(list(close)), abs=1e-6)


# ---------------------------------------------------------------------------
# 5. Missing OHLC value: the bad bar is dropped and flagged, no crash
# ---------------------------------------------------------------------------
def test_missing_ohlc_rejected(benches):
    df = df_of("ACME").copy()
    df.iloc[-5, df.columns.get_loc("High")] = float("nan")
    cleaned, dropped = boso.clean_bars(df)
    assert dropped == 1
    assert len(cleaned) == len(df) - 1
    r = boso.analyze("ACME", cleaned, benches, None, now=None)
    assert r is not None


# ---------------------------------------------------------------------------
# 6. All downloads fail: clear error, no crash, no results written
# ---------------------------------------------------------------------------
def test_all_downloads_fail(tmp_path):
    def fetch(_sym, _period=None):
        return None
    out = boso.run_screen(["AAA", "BBB"], fetch=fetch, earnings=lambda _s: None, outdir=tmp_path, now=None)
    assert out["rows"] == []
    assert "No data" in out["error"]
    assert not (tmp_path / "screener_results.csv").exists()


# ---------------------------------------------------------------------------
# 7. Same daily scan twice: no duplicate finalized snapshots
# ---------------------------------------------------------------------------
def test_no_duplicate_snapshots(tmp_path, benches):
    r = boso.analyze("ACME", df_of("ACME"), benches, None, now=None)
    f = tmp_path / "snapshots.csv"
    n1 = boso.write_snapshots([r], f, source="test")
    n2 = boso.write_snapshots([r], f, source="test")
    assert n1 == 1 and n2 == 0
    assert len(pd.read_csv(f)) == 1


def test_snapshot_has_components_and_inputs(tmp_path, benches):
    r = boso.analyze("ACME", df_of("ACME"), benches, None, now=None)
    f = tmp_path / "snapshots.csv"
    boso.write_snapshots([r], f, source="test")
    row = pd.read_csv(f).iloc[0]
    for col in ["snapshot_key", "rules_version", "engine_version", "session_status",
                "c_trend", "c_rel", "c_setup", "c_volume", "c_momentum",
                "in_price", "in_sma20", "in_sma50", "in_atr", "in_prior_high", "in_rsi", "in_vr", "in_rs_bench"]:
        assert col in row.index, col


# ---------------------------------------------------------------------------
# 8. Incomplete benchmark: score withheld
# ---------------------------------------------------------------------------
def test_incomplete_benchmark_withholds_score():
    r = boso.analyze("ACME", df_of("ACME"), {}, None, now=None)
    assert r["Breakout score"] is None
    assert r["Alignment"] == "Incomplete"
    assert "Incomplete" in r["Flags"]


# ---------------------------------------------------------------------------
# 9. Intraday: volume component N/A and score provisional, never "lower"
# ---------------------------------------------------------------------------
def test_intraday_volume_na(benches):
    df = df_of("ACME")
    last_day = df.index[-1]
    # pretend "now" is 11:00 ET on the last bar's date
    now = pd.Timestamp(last_day.date()).tz_localize("America/New_York") + pd.Timedelta(hours=11)
    r = boso.analyze("ACME", df, benches, None, now=now)
    assert r["session_status"] == "intraday"
    assert r["c_volume"] is None
    assert r["Alignment"].startswith("Provisional")
    final = boso.analyze("ACME", df, benches, None, now=None)
    # provisional score equals the final score minus the volume bucket, not less
    assert r["Breakout score"] == pytest.approx(final["Breakout score"] - final["c_volume"], abs=1)


# ---------------------------------------------------------------------------
# 10. Breakout threshold: just below / at / just above the prior 20-day high
# ---------------------------------------------------------------------------
def _force_uptrend(df: pd.DataFrame) -> pd.DataFrame:
    """Rewrite the last 60 closes as a steady rise so the trend conditions hold."""
    df = df.copy()
    base = float(df["Close"].iloc[-61])
    for i in range(60, 0, -1):
        px = base * (1.003 ** (61 - i))
        idx = df.index[-i]
        df.loc[idx, ["Open", "Close", "High", "Low"]] = [px * 0.998, px, px * 1.004, px * 0.994]
    return df


@pytest.mark.parametrize("offset,label", [(-0.001, "Breakout watch"), (0.0, "Breakout watch"), (+0.001, "Breakout confirmed")])
def test_breakout_threshold(benches, offset, label):
    df = _force_uptrend(df_of("ACME"))
    prior_high = float(df["High"].iloc[-21:-1].max())
    idx = df.index[-1]
    c = prior_high * (1 + offset)
    df.loc[idx, ["Open", "Close", "High", "Low"]] = [c * 0.999, c, max(c, prior_high) * 1.0005, c * 0.995]
    r = boso.analyze("ACME", df, benches, None, now=None)
    assert r["Setup"] == label


# ---------------------------------------------------------------------------
# 11. Python / JavaScript parity on the shared fixture
# ---------------------------------------------------------------------------
@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_parity_with_javascript(benches):
    js = subprocess.run(["node", str(Path(__file__).parent / "parity.js")], capture_output=True, text=True, check=True)
    web = json.loads(js.stdout)
    for sym in ("ACME", "UPUP"):
        py = boso.analyze(sym, df_of(sym), benches, None, now=None)
        w = web[sym]
        assert w["setup"] == py["Setup"], sym
        assert sorted(w["flags"]) == sorted(py["Flags"].split("|") if py["Flags"] else []), sym
        assert w["score"] == pytest.approx(py["Breakout score"], abs=0.5), sym
        for k, col in [("trend", "c_trend"), ("rel", "c_rel"), ("setup", "c_setup"), ("volume", "c_volume"), ("momentum", "c_momentum")]:
            assert w["sc"][k] == pytest.approx(py[col], abs=0.5), (sym, k)
        assert w["rsi"] == pytest.approx(py["RSI"], abs=0.05), sym
        assert w["atr"] == pytest.approx(py["ATR %"], abs=0.02), sym


# ---------------------------------------------------------------------------
# 12. Replay safety: with now=None, analyze() never consults the clock
# ---------------------------------------------------------------------------
def test_analyze_never_reads_clock_in_replay_mode(benches, monkeypatch):
    import datetime as _dt
    class Frozen(_dt.datetime):
        @classmethod
        def now(cls, tz=None): raise AssertionError("datetime.now called inside analyze")
        @classmethod
        def today(cls): raise AssertionError("datetime.today called inside analyze")
    class FrozenDate(_dt.date):
        @classmethod
        def today(cls): raise AssertionError("date.today called inside analyze")
    monkeypatch.setattr(boso, "datetime", Frozen)
    monkeypatch.setattr(boso, "date", FrozenDate)
    monkeypatch.setattr(pd.Timestamp, "now", classmethod(lambda cls, tz=None: (_ for _ in ()).throw(AssertionError("Timestamp.now"))))
    r = boso.analyze("ACME", df_of("ACME"), benches, None, now=None)
    assert r["session_status"] == "final"
    assert r["c_volume"] is not None


# ---------------------------------------------------------------------------
# 13. Snapshot key includes the engine version, so a corrected engine can record a revised row
# ---------------------------------------------------------------------------
def test_snapshot_key_includes_engine_version(tmp_path, benches):
    r = boso.analyze("ACME", df_of("ACME"), benches, None, now=None)
    f = tmp_path / "snapshots.csv"
    boso.write_snapshots([r], f, source="test")
    key = pd.read_csv(f)["snapshot_key"].iloc[0]
    assert boso.RULES_VERSION in key and boso.ENGINE_VERSION in key
    # a different engine version writes a new row rather than being deduped away
    monkey = boso.ENGINE_VERSION
    boso.ENGINE_VERSION = "v9.9.9-test"
    try:
        assert boso.write_snapshots([r], f, source="test") == 1
    finally:
        boso.ENGINE_VERSION = monkey
    assert len(pd.read_csv(f)) == 2
