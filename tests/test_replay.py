"""
Tests for replay.py, the historical replay of the Stock Boso rules.

    pytest -q

No network: everything runs on tests/fixtures/bars.json or small hand-built frames.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import boso
import replay

FX = json.loads((Path(__file__).parent / "fixtures" / "bars.json").read_text())
ANALYSIS_FIELDS = ["setup", "flags", "rs", "mom5", "rsi", "atr_pct"]


def df_of(sym: str) -> pd.DataFrame:
    return boso.bars_to_df(FX[sym])


def bench_dfs() -> dict[str, pd.DataFrame]:
    return {b: df_of(b) for b in ("QQQ", "SMH")}


def hand_frame(n: int, start_px: float = 100.0, step: float = 1.0, dates=None) -> pd.DataFrame:
    """Open = px, Close = px + 0.5, Low = Open - 1, High = Close + 1, rising by `step` per bar."""
    idx = pd.DatetimeIndex(dates) if dates is not None else pd.bdate_range("2026-01-05", periods=n)
    o = start_px + step * np.arange(len(idx))
    return pd.DataFrame({"Open": o, "High": o + 1.5, "Low": o - 1, "Close": o + 0.5, "Volume": 1e6}, index=idx)


# ---------------------------------------------------------------------------
# 1. No lookahead: scrambling every bar after t (stock AND benchmarks) must not
#    change anything the replay says about day t. (Same idea as freqtrade's lookahead-analysis.)
# ---------------------------------------------------------------------------
def test_no_lookahead_future_bars_do_not_change_day_t():
    ticker, benches = df_of("ACME"), bench_dfs()
    base = {r["date"]: r for r in replay.replay_ticker("ACME", ticker, benches)}
    cut = ticker.index[90]

    def scramble(df):
        df = df.copy()
        after = df.index > cut
        df.loc[after, ["Open", "High", "Low", "Close"]] *= 3.0
        df.loc[after, "Volume"] *= 10
        return df

    alt = {r["date"]: r for r in replay.replay_ticker(
        "ACME", scramble(ticker), {k: scramble(v) for k, v in benches.items()})}
    checked = 0
    for d, r in base.items():
        if pd.Timestamp(d) <= cut:
            assert {f: r[f] for f in ANALYSIS_FIELDS} == {f: alt[d][f] for f in ANALYSIS_FIELDS}, d
            checked += 1
    assert checked > 20


# ---------------------------------------------------------------------------
# 2. A replay row is exactly boso.analyze on the live-sized window ending at t
# ---------------------------------------------------------------------------
def test_replay_row_matches_direct_analyze():
    ticker, benches = df_of("UPUP"), bench_dfs()
    rows = {r["date"]: r for r in replay.replay_ticker("UPUP", ticker, benches)}
    i = 100
    t = ticker.index[i]
    window = ticker.iloc[max(0, i + 1 - replay.LOOKBACK_BARS): i + 1]
    bs = {k: boso.bench_series(boso.clean_bars(v[v.index <= t].tail(replay.LOOKBACK_BARS))[0])
          for k, v in benches.items()}
    direct = boso.analyze("UPUP", window, bs, None, None)
    r = rows[t.date().isoformat()]
    assert r["setup"] == direct["Setup"]
    assert r["rs"] == direct["RS vs bench"]
    assert r["rsi"] == direct["RSI"]
    assert "score" not in r


# ---------------------------------------------------------------------------
# 3. Date range: first row after warm-up, last row 10 sessions before the end
# ---------------------------------------------------------------------------
def test_replay_date_range():
    ticker = df_of("UPUP")
    rows = replay.replay_ticker("UPUP", ticker, bench_dfs())
    assert rows[0]["date"] == ticker.index[boso.MIN_BARS - 1].date().isoformat()
    assert rows[-1]["date"] == ticker.index[len(ticker) - 1 - replay.END_GAP].date().isoformat()


# ---------------------------------------------------------------------------
# 4. Forward returns, hand-computed
# ---------------------------------------------------------------------------
def test_forward_returns_hand_computed():
    df = hand_frame(12)
    flat = hand_frame(12, start_px=50, step=0.0)
    flat["Close"] = flat["Open"]                              # truly flat: open = close every day
    f = replay.forward_returns(df, 0, flat, horizons=(1, 5), cost_pct=0.2)
    # close -> close, descriptive: C5 / C0
    assert f["cc_5"] == pytest.approx((105.5 / 100.5 - 1) * 100)
    # next open -> close+N, executable: O1 = 101, C5 = 105.5, minus 0.2% round-trip cost
    assert f["ex_net_5"] == pytest.approx((105.5 / 101 - 1) * 100 - 0.2)
    # flat benchmark -> relative equals absolute
    assert f["rel_net_5"] == pytest.approx(f["ex_net_5"])
    # worst low while held (bars 1..5) vs entry: L1 = 100 vs O1 = 101
    assert f["mae_5"] == pytest.approx((100 / 101 - 1) * 100)
    assert f["ex_net_1"] == pytest.approx((101.5 / 101 - 1) * 100 - 0.2)


def test_forward_bench_aligned_by_date_not_position():
    """Stock is missing a session the benchmark has. The benchmark leg must use the
    stock's own entry/exit DATES, not the same row numbers."""
    all_days = pd.bdate_range("2026-01-05", periods=12)
    stock = hand_frame(11, dates=all_days.delete(3))          # skip the 4th session
    bench = hand_frame(12, start_px=200, step=10.0, dates=all_days)
    f = replay.forward_returns(stock, 0, bench, horizons=(5,), cost_pct=0.0)
    entry, exit_ = stock.index[1], stock.index[5]
    expect = (bench.loc[exit_, "Close"] / bench.loc[entry, "Open"] - 1) * 100
    assert f["bench_ex_5"] == pytest.approx(expect)


def test_forward_returns_missing_when_not_enough_future_bars():
    df = hand_frame(4)
    f = replay.forward_returns(df, 0, df, horizons=(5,), cost_pct=0.2)
    assert f["ex_net_5"] is None and f["cc_5"] is None


# ---------------------------------------------------------------------------
# 5. Episodes: only the first day of a run of the same setup counts
# ---------------------------------------------------------------------------
def test_mark_episodes():
    rows = [{"ticker": "A", "date": d, "setup": s} for d, s in
            [("2026-01-01", "No setup"), ("2026-01-02", "Breakout watch"), ("2026-01-05", "Breakout watch"),
             ("2026-01-06", "No setup"), ("2026-01-07", "Breakout watch")]]
    rows.append({"ticker": "B", "date": "2026-01-02", "setup": "Breakout watch"})
    replay.mark_episodes(rows)
    a = [r["episode_start"] for r in rows if r["ticker"] == "A"]
    assert a == [True, True, False, True, True]
    assert rows[-1]["episode_start"] is True


# ---------------------------------------------------------------------------
# 6. Rankers pick from the SAME eligible universe (RS available); ties broken by ticker
# ---------------------------------------------------------------------------
def test_top_n_same_universe_and_ties():
    day = [
        {"ticker": "A", "rs": 1.0, "mom5": 9.0},
        {"ticker": "B", "rs": 5.0, "mom5": 1.0},
        {"ticker": "C", "rs": 4.0, "mom5": 2.0},
        {"ticker": "D", "rs": 3.0, "mom5": 3.0},
        {"ticker": "E", "rs": None, "mom5": 99.0},   # incomplete: not eligible for anyone
    ]
    assert [r["ticker"] for r in replay.top_n(day, "rs")] == ["B", "C", "D"]
    assert [r["ticker"] for r in replay.top_n(day, "mom5")] == ["A", "D", "C"]


def test_daily_portfolios_skip_thin_days():
    rows = [{"date": "2026-01-02", "ticker": t, "rs": s, "mom5": s, "rel_net_5": s / 10}
            for t, s in [("A", 30), ("B", 20), ("C", 10), ("D", 0)]]
    rows += [{"date": "2026-01-05", "ticker": "A", "rs": 1, "mom5": 1, "rel_net_5": 1.0}]
    p = replay.daily_portfolios(rows, horizon=5)
    assert list(p.index) == ["2026-01-02"]
    assert p.loc["2026-01-02", "rs"] == pytest.approx(2.0)         # mean of 3, 2, 1
    assert p.loc["2026-01-02", "all"] == pytest.approx(1.5)        # all eligible


# ---------------------------------------------------------------------------
# 7. Block bootstrap: deterministic with a seed; a constant series has a zero-width interval
# ---------------------------------------------------------------------------
def test_block_bootstrap():
    x = np.random.default_rng(1).normal(0.5, 1.0, 300)
    a = replay.block_bootstrap(x, block=10, n_boot=500, seed=7)
    b = replay.block_bootstrap(x, block=10, n_boot=500, seed=7)
    assert a == b
    assert a["lo"] < a["mean"] < a["hi"]
    c = replay.block_bootstrap(np.full(50, 0.3), block=10, n_boot=200, seed=0)
    assert c["lo"] == pytest.approx(0.3) and c["hi"] == pytest.approx(0.3) and c["p_pos"] == 1.0


# ---------------------------------------------------------------------------
# 8. Holdout: the most recent 12 months are kept out of the development scorecard
# ---------------------------------------------------------------------------
def test_split_holdout():
    rows = [{"date": d} for d in ["2024-01-02", "2025-10-24", "2025-10-27", "2026-10-16"]]
    dev, hold, start = replay.split_holdout(rows, last_date="2026-10-16", months=12)
    assert start == "2025-10-16"
    assert [r["date"] for r in dev] == ["2024-01-02"]
    assert [r["date"] for r in hold] == ["2025-10-24", "2025-10-27", "2026-10-16"]
