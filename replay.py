"""
replay.py — historical replay of Stock Boso rules v2.1
=======================================================
Walks back through years of daily bars and asks, for every past session t:
"what would the screener have said using only bars up to t, and what happened next?"

    python replay.py              # development period only (holdout stays hidden)
    python replay.py --holdout    # ALSO evaluate the untouched last 12 months. Do this once, at the end.

Outputs (in this folder, gitignored):
    replay_results.csv   one row per ticker per session: setup, score, components, forward returns
    scorecard.md         the readable verdict
    replay_data/         cached Yahoo bars (personal research copy; do not publish)

Two kinds of forward return, labelled everywhere:
    cc_N      close(t) -> close(t+N). Descriptive: you could not actually buy at that close.
    ex_net_N  open(t+1) -> close(t+N), minus COST_PCT. Executable: buy next morning, sell N sessions later.
    rel_*     the same, minus the benchmark (SMH for semis, QQQ otherwise) over the same dates.

The rules are not changed or tuned here. This only measures them.
"""

from __future__ import annotations

import argparse
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import boso

LOOKBACK_BARS = 126        # ~6 months, the same window the live screener downloads
END_GAP = 10               # stop 10 sessions before the end so every horizon has its outcome
HORIZONS = (1, 3, 5, 10)
PRIMARY = 5                # the 5-session horizon decides; 1/3/10 are context
COST_PCT = 0.20            # round trip, %: ~0.10 commission/spread + ~0.10 slippage
TOP_N = 3
LARGE_LOSS_PCT = -5.0      # a single trade losing more than this counts as a large loss
HOLDOUT_MONTHS = 12
BOOT_BLOCK = 10            # sessions per bootstrap block (5-day trades overlap, so days are not independent)
BOOT_N = 2000
RANKERS = ("score", "rs", "mom5")
RANKER_NAMES = {"score": "Top 3 by breakout score", "rs": "Top 3 by RS vs bench",
                "mom5": "Top 3 by 5-day momentum", "all": "All eligible (equal weight)"}


# ---------------------------------------------------------------------------
# Replay one ticker — nothing after t is visible when analysing t
# ---------------------------------------------------------------------------
def benches_at(bench_dfs: dict[str, pd.DataFrame], t: pd.Timestamp, lookback: int, cache: dict) -> dict:
    """Benchmark state as of date t, built only from benchmark bars on or before t."""
    if t not in cache:
        out = {}
        for name, bdf in bench_dfs.items():
            sub = bdf.iloc[: bdf.index.searchsorted(t, side="right")].tail(lookback)
            sub, _ = boso.clean_bars(sub)
            if len(sub) >= boso.MIN_BARS:
                out[name] = boso.bench_series(sub)
        cache[t] = out
    return cache[t]


def _num(x) -> float | None:
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)


def forward_returns(df: pd.DataFrame, i: int, bench_df: pd.DataFrame | None,
                    horizons=HORIZONS, cost_pct: float = COST_PCT) -> dict:
    """Outcomes after the signal on bar i. The benchmark leg uses the stock's own dates."""
    out: dict = {}
    for n in horizons:
        keys = [f"{k}_{n}" for k in ("cc", "ex_net", "mae", "bench_cc", "bench_ex", "rel_cc", "rel_net")]
        out.update(dict.fromkeys(keys))
        if i + n >= len(df):
            continue
        c0, cn, o1 = df["Close"].iloc[i], df["Close"].iloc[i + n], df["Open"].iloc[i + 1]
        low = df["Low"].iloc[i + 1: i + n + 1].min()
        if not (c0 > 0 and o1 > 0 and cn > 0):
            continue
        cc, ex_net = boso.pct(cn, c0), boso.pct(cn, o1) - cost_pct
        out.update({f"cc_{n}": _num(cc), f"ex_net_{n}": _num(ex_net), f"mae_{n}": _num(boso.pct(low, o1))})
        if bench_df is None:
            continue
        t, entry, exit_ = df.index[i], df.index[i + 1], df.index[i + n]
        bc0, bcn = bench_df["Close"].asof(t), bench_df["Close"].asof(exit_)
        bo1 = bench_df["Open"].get(entry)                      # exact date only: no stale open
        if _num(bc0) and _num(bcn):
            out[f"bench_cc_{n}"] = boso.pct(bcn, bc0)
            out[f"rel_cc_{n}"] = cc - out[f"bench_cc_{n}"]
        if _num(bo1) and _num(bcn):
            out[f"bench_ex_{n}"] = boso.pct(bcn, bo1)
            out[f"rel_net_{n}"] = ex_net - out[f"bench_ex_{n}"]
    return out


def replay_ticker(ticker: str, df: pd.DataFrame, bench_dfs: dict[str, pd.DataFrame],
                  lookback: int = LOOKBACK_BARS, cost_pct: float = COST_PCT, cache: dict | None = None) -> list[dict]:
    cache = {} if cache is None else cache
    bname = boso.bench_for(ticker)
    rows = []
    for i in range(boso.MIN_BARS - 1, len(df) - END_GAP):
        t = df.index[i]
        window = df.iloc[max(0, i + 1 - lookback): i + 1]     # bars up to and including t, nothing later
        benches = benches_at(bench_dfs, t, lookback, cache)
        r = boso.analyze(ticker, window, benches, None, None)  # earnings unknown, clock never consulted
        if r is None:
            continue
        q = benches.get("QQQ")
        rows.append({
            "date": t.date().isoformat(), "ticker": ticker, "bench": bname,
            "setup": r["Setup"], "flags": r["Flags"], "score": r["Breakout score"], "alignment": r["Alignment"],
            "c_trend": r["c_trend"], "c_rel": r["c_rel"], "c_setup": r["c_setup"],
            "c_volume": r["c_volume"], "c_momentum": r["c_momentum"],
            "rs": r["RS vs bench"], "mom5": r["5d %"], "rsi": r["RSI"], "atr_pct": r["ATR %"],
            "qqq_above_sma50": None if q is None else q["above_sma50"],
            **forward_returns(df, i, bench_dfs.get(bname), HORIZONS, cost_pct),
        })
    return rows


def mark_episodes(rows: list[dict]) -> list[dict]:
    """episode_start = True on the first day a ticker enters a setup (not on every repeated day)."""
    prev: dict[str, str] = {}
    for r in sorted(rows, key=lambda r: (r["ticker"], r["date"])):
        r["episode_start"] = prev.get(r["ticker"]) != r["setup"]
        prev[r["ticker"]] = r["setup"]
    return rows


# ---------------------------------------------------------------------------
# Ranking and portfolios — every ranker draws from the same eligible universe
# ---------------------------------------------------------------------------
def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def top_n(day_rows: list[dict], key: str, n: int = TOP_N) -> list[dict]:
    eligible = [r for r in day_rows if _ok(r.get("score")) and _ok(r.get(key))]
    return sorted(eligible, key=lambda r: (-r[key], r["ticker"]))[:n]


def picks(rows: list[dict], key: str, horizon: int = PRIMARY, n: int = TOP_N) -> list[dict]:
    """Every (date, ticker) the ranker would have picked, on days with at least n eligible names."""
    out = []
    for _, day in _by_date(rows, horizon, n):
        out += top_n(day, key, n) if key != "all" else day
    return out


def _by_date(rows: list[dict], horizon: int, n: int):
    days: dict[str, list[dict]] = {}
    for r in rows:
        if _ok(r.get("score")) and _ok(r.get(f"rel_net_{horizon}")):
            days.setdefault(r["date"], []).append(r)
    for d in sorted(days):
        if len(days[d]) >= n:
            yield d, days[d]


def daily_portfolios(rows: list[dict], horizon: int = PRIMARY, n: int = TOP_N) -> pd.DataFrame:
    """Mean benchmark-relative net return per day for each ranker, plus the all-eligible baseline."""
    col = f"rel_net_{horizon}"
    rec = {}
    for d, day in _by_date(rows, horizon, n):
        rec[d] = {k: float(np.mean([r[col] for r in top_n(day, k, n)])) for k in RANKERS}
        rec[d]["all"] = float(np.mean([r[col] for r in day]))
    return pd.DataFrame.from_dict(rec, orient="index", columns=[*RANKERS, "all"])


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def block_bootstrap(x, block: int = BOOT_BLOCK, n_boot: int = BOOT_N, seed: int = 0, ci: float = 0.90) -> dict:
    """Circular block bootstrap of the mean. Keeps runs of neighbouring days together,
    because overlapping 5-day trades make day-to-day results correlated."""
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    n = len(x)
    if n == 0:
        return {"mean": float("nan"), "lo": float("nan"), "hi": float("nan"), "p_pos": float("nan"), "n": 0}
    block = max(1, min(block, n))
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(n_boot, math.ceil(n / block)))
    idx = ((starts[:, :, None] + np.arange(block)) % n).reshape(n_boot, -1)[:, :n]
    means = x[idx].mean(axis=1)
    a = (1 - ci) / 2
    return {"mean": float(x.mean()), "lo": float(np.quantile(means, a)), "hi": float(np.quantile(means, 1 - a)),
            "p_pos": float((means > 0).mean()), "n": n}


def rank_ic(rows: list[dict], key: str, horizon: int = PRIMARY, min_names: int = 5) -> pd.Series:
    """Per-day Spearman correlation between a ranking key and the next-N benchmark-relative return."""
    col, out = f"rel_net_{horizon}", {}
    for d, day in _by_date(rows, horizon, min_names):
        day = [r for r in day if _ok(r.get(key))]
        if len(day) < min_names:
            continue
        s = pd.DataFrame({"k": [r[key] for r in day], "y": [r[col] for r in day]}).rank()
        if s["k"].nunique() > 1 and s["y"].nunique() > 1:
            out[d] = float(s["k"].corr(s["y"]))
    return pd.Series(out, dtype=float)


def trade_stats(vals: list[float], mae: list[float]) -> dict:
    v = np.asarray([x for x in vals if _ok(x)], dtype=float)
    m = np.asarray([x for x in mae if _ok(x)], dtype=float)
    if len(v) == 0:
        return {"n": 0}
    wins, losses = v[v > 0], v[v <= 0]
    return {"n": len(v), "mean": v.mean(), "win_rate": len(wins) / len(v) * 100,
            "avg_win": wins.mean() if len(wins) else float("nan"),
            "avg_loss": losses.mean() if len(losses) else float("nan"),
            "large_loss": (v <= LARGE_LOSS_PCT).mean() * 100,
            "mae_med": np.median(m) if len(m) else float("nan"),
            "mae_p10": np.quantile(m, 0.10) if len(m) else float("nan")}


def split_holdout(rows: list[dict], last_date: str, months: int = HOLDOUT_MONTHS):
    start = (pd.Timestamp(last_date) - pd.DateOffset(months=months)).date().isoformat()
    return [r for r in rows if r["date"] < start], [r for r in rows if r["date"] >= start], start


# ---------------------------------------------------------------------------
# Scorecard
# ---------------------------------------------------------------------------
def _f(x, d: int = 2, signed: bool = True) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    return f"{x:+.{d}f}" if signed else f"{x:.{d}f}"


def verdict(rows: list[dict]) -> tuple[bool, str, dict]:
    """The decision rule, fixed before any results were seen:
    the score passes only if, at the 5-session horizon, executable, benchmark-relative, after costs,
      (a) its mean daily return beats top-3-by-RS,
      (b) the bootstrap puts at least 90% probability on that difference being above zero, and
      (c) it beats RS in at least two thirds of the calendar years covered."""
    p = daily_portfolios(rows, PRIMARY)
    diff = p["score"] - p["rs"]
    bs = block_bootstrap(diff.to_numpy())
    years = diff.groupby(pd.to_datetime(diff.index).year).mean()
    yrs_up = int((years > 0).sum())
    ok = bs["mean"] > 0 and bs["p_pos"] >= 0.90 and yrs_up >= math.ceil(len(years) * 2 / 3)
    why = (f"score − RS = {_f(bs['mean'], 3)}% per trade-day (90% interval {_f(bs['lo'], 3)} to {_f(bs['hi'], 3)}), "
           f"P(>0) = {bs['p_pos']:.0%}, ahead in {yrs_up} of {len(years)} years")
    return ok, why, {"bs": bs, "years": years}


def section(rows: list[dict], title: str) -> list[str]:
    L = [f"## {title}", ""]
    if not rows:
        return L + ["No rows.", ""]
    p = daily_portfolios(rows, PRIMARY)
    if p.empty:
        return L + ["Not enough eligible names on any day.", ""]
    ok, why, v = verdict(rows)
    L += [f"**Verdict: {'the score BEATS RS-alone' if ok else 'the score does NOT beat RS-alone'}** — {why}.", ""]
    L += ["Decision rule (agreed in advance): if the score does not beat RS-alone after costs with reasonable "
          "stability, drop the composite and keep the indicators.", ""]

    L += [f"### Headline: {PRIMARY}-session, executable (next open → close), net of {COST_PCT}% costs", "",
          f"{len(p)} trading days. 'vs bench' = return minus SMH/QQQ over the same dates. "
          "Win rate and win/loss are absolute (did the trade itself make money).", "",
          "| Ranking | mean vs bench % | 90% interval | win rate | avg win % | avg loss % | "
          f"large losses (≤{LARGE_LOSS_PCT:.0f}%) | MAE median % | MAE worst 10% | mean at 2× costs |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for k in (*RANKERS, "all"):
        bs = block_bootstrap(p[k].to_numpy())
        pk = picks(rows, k)
        s = trade_stats([r[f"ex_net_{PRIMARY}"] for r in pk], [r[f"mae_{PRIMARY}"] for r in pk])
        L.append(f"| {RANKER_NAMES[k]} | {_f(bs['mean'])} | {_f(bs['lo'])} to {_f(bs['hi'])} | "
                 f"{_f(s.get('win_rate'), 0, False)}% | {_f(s.get('avg_win'))} | {_f(s.get('avg_loss'))} | "
                 f"{_f(s.get('large_loss'), 1, False)}% | {_f(s.get('mae_med'))} | {_f(s.get('mae_p10'))} | "
                 f"{_f(bs['mean'] - COST_PCT)} |")
    L.append("")

    L += ["### Head to head at every horizon (score minus the alternative, executable, vs bench, net)", "",
          "| Horizon | score − RS | P(>0) | score − momentum | P(>0) | score top-3, close→close (descriptive) |",
          "|---|---|---|---|---|---|"]
    for h in HORIZONS:
        ph = daily_portfolios(rows, h)
        if ph.empty:
            continue
        a, b = block_bootstrap((ph["score"] - ph["rs"]).to_numpy()), block_bootstrap((ph["score"] - ph["mom5"]).to_numpy())
        cc = np.nanmean([r[f"rel_cc_{h}"] if _ok(r.get(f"rel_cc_{h}")) else np.nan for r in picks(rows, "score", h)])
        L.append(f"| {h}d{' (primary)' if h == PRIMARY else ''} | {_f(a['mean'], 3)} | {a['p_pos']:.0%} | "
                 f"{_f(b['mean'], 3)} | {b['p_pos']:.0%} | {_f(cc, 3)} |")
    L.append("")

    L += [f"### Does a higher number mean a better {PRIMARY}-day result? (rank IC)", "",
          "Rank IC = how well each day's ordering matched the next 5 days' ordering. 0 = no relationship, "
          "+1 = perfect. Values around +0.05 are already considered useful in practice.", "",
          "| Ranking key | mean IC | 90% interval | days with IC > 0 |", "|---|---|---|---|"]
    for k in RANKERS:
        ic = rank_ic(rows, k)
        bs = block_bootstrap(ic.to_numpy())
        L.append(f"| {k} | {_f(bs['mean'], 3)} | {_f(bs['lo'], 3)} to {_f(bs['hi'], 3)} | "
                 f"{_f((ic > 0).mean() * 100 if len(ic) else float('nan'), 0, False)}% |")
    L.append("")

    L += ["### By setup label (distinct episodes: the first day a ticker enters the setup)", "",
          "| Setup | episodes | mean vs bench % | win rate | avg win % | avg loss % | large losses | MAE worst 10% |",
          "|---|---|---|---|---|---|---|---|"]
    for setup in boso.SETUP_RANK:
        ep = [r for r in rows if r.get("episode_start") and r["setup"] == setup]
        s = trade_stats([r[f"ex_net_{PRIMARY}"] for r in ep], [r[f"mae_{PRIMARY}"] for r in ep])
        rel = [r[f"rel_net_{PRIMARY}"] for r in ep if _ok(r.get(f"rel_net_{PRIMARY}"))]
        L.append(f"| {setup} | {s['n']} | {_f(np.mean(rel) if rel else float('nan'))} | "
                 f"{_f(s.get('win_rate'), 0, False)}% | {_f(s.get('avg_win'))} | {_f(s.get('avg_loss'))} | "
                 f"{_f(s.get('large_loss'), 1, False)}% | {_f(s.get('mae_p10'))} |")
    L.append("")

    L += ["### By score bucket (all scored ticker-days)", "",
          "| Bucket | ticker-days | mean vs bench % | win rate |", "|---|---|---|---|"]
    for name, lo, hi in [("Strong ≥75", 75, 101), ("Moderate 55–74", 55, 75), ("Mixed 35–54", 35, 55), ("Weak <35", -1, 35)]:
        b = [r for r in rows if _ok(r.get("score")) and lo <= r["score"] < hi]
        s = trade_stats([r[f"ex_net_{PRIMARY}"] for r in b], [])
        rel = [r[f"rel_net_{PRIMARY}"] for r in b if _ok(r.get(f"rel_net_{PRIMARY}"))]
        L.append(f"| {name} | {s['n']} | {_f(np.mean(rel) if rel else float('nan'))} | "
                 f"{_f(s.get('win_rate'), 0, False)}% |")
    L.append("")

    diff = p["score"] - p["rs"]
    L += ["### Stability", "", "| Period | days | score − RS % | score % | RS % |", "|---|---|---|---|---|"]
    yr = pd.to_datetime(p.index).year
    for y in sorted(set(yr)):
        g = p[yr == y]
        L.append(f"| {y} | {len(g)} | {_f((g['score'] - g['rs']).mean(), 3)} | {_f(g['score'].mean())} | {_f(g['rs'].mean())} |")
    reg = {r["date"]: r["qqq_above_sma50"] for r in rows if r.get("qqq_above_sma50") is not None}
    for label, want in [("QQQ above its SMA50", True), ("QQQ below its SMA50", False)]:
        g = p[[reg.get(d) is want for d in p.index]]
        if len(g):
            L.append(f"| {label} | {len(g)} | {_f((g['score'] - g['rs']).mean(), 3)} | {_f(g['score'].mean())} | {_f(g['rs'].mean())} |")
    L.append("")
    return L


def scorecard(dev: list[dict], hold: list[dict], holdout_start: str, show_holdout: bool, meta: dict) -> str:
    L = ["# Stock Boso — replay scorecard", "",
         f"Rules {boso.RULES_VERSION} · engine {boso.ENGINE_VERSION} · generated {meta['generated']}  ",
         f"Universe: {', '.join(meta['tickers'])} (benchmarks QQQ, SMH)  ",
         f"Bars: {meta['first']} to {meta['last']} (Yahoo, auto-adjusted). Signals stop {END_GAP} sessions before the end.  ",
         f"Development period: up to {holdout_start}. Holdout (untouched): {holdout_start} onward — "
         f"{'SHOWN below' if show_holdout else 'hidden; run `python replay.py --holdout` once, at the end'}.", "",
         "**Read this first**", "",
         "- This is research, not a trading signal. Past results do not predict future ones.",
         "- **Survivorship bias:** the 20 names were picked in 2026, knowing they mattered. Absolute returns are "
         "flattered. The fair comparison is *between rankings on the same names and days*, which is what the verdict uses.",
         "- Earnings dates are not known historically, so the Earnings flag never fires here.",
         f"- Costs: {COST_PCT}% per round trip on every trade. Each day's top 3 is treated as a fresh {PRIMARY}-day trade; "
         "real holding would overlap and trade less often.",
         "- Comparisons run: 3 rankings × 4 horizons, plus setup and bucket tables. With that many looks, one "
         "'good-looking' number by itself means little. Only the primary verdict line counts.", ""]
    L += section(dev, "Development period")
    if show_holdout:
        L += section(hold, "Holdout period (last 12 months, evaluated once)")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Data and command line
# ---------------------------------------------------------------------------
DATA_DIR = Path("replay_data")


def load_bars(ticker: str, years: int, refresh: bool) -> pd.DataFrame | None:
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"{ticker}.csv"
    if path.exists() and not refresh:
        return pd.read_csv(path, index_col=0, parse_dates=True)
    import yfinance as yf
    try:
        df = yf.download(ticker, period=f"{years}y", progress=False, auto_adjust=True)
    except Exception as e:
        print(f"  {ticker}: download failed ({e})")
        return None
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.to_csv(path)
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--years", type=int, default=5)
    ap.add_argument("--holdout", action="store_true", help="also evaluate the untouched last 12 months")
    ap.add_argument("--refresh", action="store_true", help="re-download bars instead of using replay_data/")
    args = ap.parse_args()

    from stock_screener import WATCHLIST
    print(f"Loading {args.years}y of bars...")
    bench_dfs = {b: load_bars(b, args.years, args.refresh) for b in boso.BENCHMARKS}
    if any(v is None for v in bench_dfs.values()):
        raise SystemExit("A benchmark failed to download; nothing replayed.")

    rows, cache, used = [], {}, []
    for t in WATCHLIST:
        df = load_bars(t, args.years, args.refresh)
        if df is None or len(df) < boso.MIN_BARS + END_GAP:
            print(f"  {t}: not enough bars, skipped")
            continue
        r = replay_ticker(t, df, bench_dfs, cache=cache)
        print(f"  {t}: {len(r)} sessions from {r[0]['date'] if r else '-'}")
        rows += r
        used.append(t)
    mark_episodes(rows)

    last = max(r["date"] for r in rows)
    dev, hold, start = split_holdout(rows, last)
    out = dev + (hold if args.holdout else [])
    pd.DataFrame(out).sort_values(["date", "ticker"]).to_csv("replay_results.csv", index=False)
    meta = {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "tickers": used,
            "first": min(r["date"] for r in rows), "last": last}
    Path("scorecard.md").write_text(scorecard(dev, hold, start, args.holdout, meta), encoding="utf-8")
    ok, why, _ = verdict(dev)
    print(f"\n{len(out)} rows -> replay_results.csv; scorecard -> scorecard.md")
    print(f"Development verdict: {'score BEATS RS-alone' if ok else 'score does NOT beat RS-alone'} ({why})")
    if not args.holdout:
        print(f"Holdout from {start} is untouched. Run with --holdout once you are done looking.")


if __name__ == "__main__":
    main()
