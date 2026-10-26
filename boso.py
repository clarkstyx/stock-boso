"""
boso.py — Stock Boso engine (rules v2.1, engine v2.1.1)
========================================================
Pure logic, no network. stock_screener.py wraps this for the command line;
tests/test_boso.py exercises it directly; index.html mirrors it in JavaScript
and tests/parity.js checks the two agree.

Rules version changes only when the strategy changes.
Engine version changes when a calculation or data-handling defect is fixed.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from pathlib import Path
from typing import Callable

import pandas as pd

RULES_VERSION = "v2.1"
ENGINE_VERSION = "v2.1.1"

BENCHMARKS = ["QQQ", "SMH"]
SEMIS = {"NVDA", "AMD", "AVGO", "TSM", "MU", "INTC", "ARM", "MRVL", "QCOM", "SMCI",
         "TXN", "ADI", "LRCX", "AMAT", "KLAC", "ASML", "ON", "MCHP", "NXPI", "MPWR"}
EARNINGS_WARN_DAYS = 7
MIN_BARS = 61
SETUP_RANK = {"Breakout confirmed": 0, "Breakout watch": 1, "Pullback watch": 2, "Downtrend": 4, "No setup": 5}


def bench_for(ticker: str) -> str:
    return "SMH" if ticker in SEMIS else "QQQ"


# ---------------------------------------------------------------------------
# Data shaping and guards
# ---------------------------------------------------------------------------
def bars_to_df(bars: list[dict]) -> pd.DataFrame:
    """Fixture/JSON bars ({d,o,h,l,c,v}) -> DataFrame indexed by date."""
    df = pd.DataFrame(bars).rename(columns={"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"})
    df.index = pd.to_datetime(df["d"])
    return df[["Open", "High", "Low", "Close", "Volume"]].astype(float)


def clean_bars(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Drop bars with missing or impossible OHLC. Returns (clean, dropped_count)."""
    ok = df[["Open", "High", "Low", "Close"]].notna().all(axis=1)
    ok &= (df["High"] >= df["Low"]) & (df["Close"] > 0) & (df["High"] > 0)
    cleaned = df[ok].copy()
    cleaned["Volume"] = cleaned["Volume"].fillna(0)
    return cleaned, int((~ok).sum())


# ---------------------------------------------------------------------------
# Indicators — Wilder smoothing seeded with a simple average (TradingView RMA)
# ---------------------------------------------------------------------------
def rsi_wilder(close: pd.Series, n: int = 14) -> float:
    c = close.to_numpy(dtype=float)
    if len(c) < n + 1:
        return float("nan")
    g = l = 0.0
    for i in range(1, n + 1):
        d = c[i] - c[i - 1]
        g += max(d, 0.0); l += max(-d, 0.0)
    g /= n; l /= n
    for i in range(n + 1, len(c)):
        d = c[i] - c[i - 1]
        g = (g * (n - 1) + max(d, 0.0)) / n
        l = (l * (n - 1) + max(-d, 0.0)) / n
    if l == 0:
        return 100.0
    return 100 - 100 / (1 + g / l)


def atr_wilder(df: pd.DataFrame, n: int = 14) -> float:
    h, l, c = df["High"].to_numpy(float), df["Low"].to_numpy(float), df["Close"].to_numpy(float)
    if len(c) < n + 1:
        return float("nan")
    tr = lambda i: max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    a = sum(tr(i) for i in range(1, n + 1)) / n
    for i in range(n + 1, len(c)):
        a = (a * (n - 1) + tr(i)) / n
    return float(a)


def pct(a: float, b: float) -> float:
    return (a / b - 1) * 100


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def ramp(x: float, x0: float, x1: float) -> float:
    return clamp((x - x0) / (x1 - x0), 0, 1)


# ---------------------------------------------------------------------------
# Benchmarks — keep the close series so returns can be aligned by DATE
# ---------------------------------------------------------------------------
def bench_series(df: pd.DataFrame) -> dict:
    close = df["Close"]
    sma50 = float(close.tail(50).mean())
    sma50_prev = float(close.iloc[-60:-10].mean())
    return {"close": close, "above_sma50": float(close.iloc[-1]) > sma50, "sma50_rising": sma50 > sma50_prev}


def bench_return(b: dict, start: pd.Timestamp, end: pd.Timestamp) -> float | None:
    """Benchmark return between two dates using the last available close on or before each."""
    s, e = b["close"].asof(start), b["close"].asof(end)
    if s is None or e is None or pd.isna(s) or pd.isna(e) or s <= 0:
        return None
    return pct(float(e), float(s))


# ---------------------------------------------------------------------------
# Session status
# ---------------------------------------------------------------------------
def session_status(last_bar_date: date, now: pd.Timestamp | None) -> str:
    """'final' when the latest bar is a completed session, 'intraday' while the US market is open on that date.
    now=None means 'evaluate as a completed session' (used by tests and the replay engine)."""
    if now is None:
        return "final"
    et = now.tz_convert("America/New_York") if now.tzinfo else now.tz_localize("America/New_York")
    mins = et.hour * 60 + et.minute
    return "intraday" if (et.date() == last_bar_date and 570 <= mins < 960) else "final"


# ---------------------------------------------------------------------------
# The rules — v2.1, mirror of index.html analyze()
# ---------------------------------------------------------------------------
def analyze(ticker: str, df: pd.DataFrame, benches: dict[str, dict], earnings: date | None,
            now: pd.Timestamp | None) -> dict | None:
    df, dropped = clean_bars(df)
    if len(df) < MIN_BARS:
        return None
    close = df["Close"]
    last = df.iloc[-1]
    c, prev_c = float(last["Close"]), float(close.iloc[-2])
    last_date = df.index[-1].date()
    status = session_status(last_date, now)

    prior = df.iloc[-21:-1]                                   # t-20 .. t-1, excludes today
    ph, pl = float(prior["High"].max()), float(prior["Low"].min())
    atr = atr_wilder(df)
    sma20, sma50 = float(close.tail(20).mean()), float(close.tail(50).mean())
    sma20_prev, sma50_prev = float(close.iloc[-25:-5].mean()), float(close.iloc[-60:-10].mean())
    completed = df.iloc[-21:-1]
    dollar_vol = float((completed["Close"] * completed["Volume"]).mean()) / 1e6
    base_vol = float(completed["Volume"].mean())
    vr = float(last["Volume"]) / base_vol if base_vol > 0 else None
    hi, lo = float(last["High"]), float(last["Low"])
    close_loc = (c - lo) / (hi - lo) if hi > lo else 0.5
    d1, d5, d20 = pct(c, prev_c), pct(c, float(close.iloc[-6])), pct(c, float(close.iloc[-21]))
    prev5 = pct(float(close.iloc[-6]), float(close.iloc[-11]))
    rsi = rsi_wilder(close)

    flags: list[str] = []
    invalid = not (atr > 0) or math.isnan(rsi)
    if invalid:
        flags.append("Invalid data")
    if dropped:
        flags.append(f"Dropped {dropped} bar{'s' if dropped > 1 else ''}")

    bname = bench_for(ticker)
    B, BQ = benches.get(bname), benches.get("QQQ")
    start_ts, end_ts = df.index[-21], df.index[-1]
    rb = bench_return(B, start_ts, end_ts) if B else None
    rq = bench_return(BQ, start_ts, end_ts) if BQ else None
    rs_b = d20 - rb if rb is not None else None
    rs_q = d20 - rq if rq is not None else None
    atr_pct = atr / c * 100 if atr > 0 else None
    rs_norm = rs_b / atr_pct if (rs_b is not None and atr_pct) else None
    edays = (earnings - last_date).days if earnings else None
    range_pos = 0.5 if ph == pl else (c - pl) / (ph - pl)
    dist_sma20 = (c - sma20) / atr if atr > 0 else None

    # ----- label (one) -----
    if invalid:
        setup = "No setup"
    else:
        up = c > sma20 > sma50 and sma20 > sma20_prev
        if up and c > ph:
            setup = "Breakout confirmed"
        elif up and (ph - c) <= atr and range_pos >= 0.85:
            setup = "Breakout watch"
        elif (sma20 > sma50 and sma50 > sma50_prev and c > sma50 and -1.5 <= dist_sma20 <= 0.5
              and 40 <= rsi <= 60 and (rs_norm is None or rs_norm >= -1)):
            setup = "Pullback watch"
        elif c < sma20 < sma50:
            setup = "Downtrend"
        else:
            setup = "No setup"

    # ----- flags (any number) -----
    if not invalid and (dist_sma20 > 2.5 or rsi > 75):
        flags.append("Extended")
    if vr is not None and vr >= 1.5 and close_loc < 0.4 and c < prev_c and status == "final":
        flags.append("Heavy selling")
    if edays is not None and 0 <= edays <= EARNINGS_WARN_DAYS:
        flags.append("Earnings")
    if rs_b is None:
        flags.append("Incomplete")

    # ----- breakout alignment score. Five buckets. NOT a probability. -----
    if invalid:
        parts = {"trend": None, "rel": None, "setup": None, "volume": None, "momentum": None}
    else:
        vol_confirm = close_loc >= 0.5 and c >= prev_c
        parts = {
            "trend": (8 if c > sma20 else 0) + (8 if sma20 > sma50 else 0)
                     + (5 if sma20 > sma20_prev else 0) + (4 if sma50 > sma50_prev else 0),
            "rel": None if rs_norm is None else
                   ramp(rs_norm, 0, 2.5) * 15 + (6 if B["above_sma50"] else 0) + (4 if B["sma50_rising"] else 0),
            "setup": ramp(range_pos, 0.6, 1) * 10 + (5 if ph - c <= atr else 0) + (5 if c > ph else 0),
            # Volume is N/A while the session is open: a partial reading is not a bearish signal
            "volume": None if (status == "intraday" or vr is None) else (ramp(vr, 0.8, 2) * 15 if vol_confirm else 0),
            "momentum": (0 if rsi < 40 else ramp(rsi, 40, 55) * 8 if rsi < 55 else 8 if rsi <= 68
                         else (1 - ramp(rsi, 68, 78)) * 8 if rsi < 78 else 0)
                        + (4 if d5 > 0 else 0) + (3 if d5 > prev5 and d5 > 0 else 0),
        }

    if invalid:
        score, align = None, "Invalid data"
    elif parts["rel"] is None:
        score, align = None, "Incomplete"
    elif parts["volume"] is None:
        score = round(parts["trend"] + parts["rel"] + parts["setup"] + parts["momentum"])
        align = "Provisional (intraday, volume n/a, max 85)"
    else:
        score = round(sum(parts.values()))
        align = ("Strong alignment" if score >= 75 else "Moderate alignment" if score >= 55
                 else "Mixed signals" if score >= 35 else "Weak alignment")

    r2 = lambda x: None if x is None else round(x, 2)
    return {
        "Ticker": ticker, "Setup": setup, "Flags": "|".join(flags),
        "Breakout score": score, "Alignment": align,
        "Score breakdown": " · ".join(f"{k} {'n/a' if v is None else f'{v:.0f}'}" for k, v in parts.items()),
        "Bench": bname, "RS vs bench": r2(rs_b), "RS vs QQQ": r2(rs_q),
        "Earnings in (d)": edays, "Earnings date": earnings.isoformat() if earnings else "",
        "Price": round(c, 2), "1d %": round(d1, 2), "5d %": round(d5, 2), "20d %": round(d20, 2),
        "ATR %": r2(atr_pct), "RSI": None if math.isnan(rsi) else round(rsi, 1),
        "vs SMA20 %": round(pct(c, sma20), 2), "vs SMA50 %": round(pct(c, sma50), 2),
        "Prior 20d range pos": round(range_pos * 100, 1), "Prior 20d high": round(ph, 2),
        "Avg $Vol (M)": round(dollar_vol, 1), "Vol vs avg": r2(vr),
        "Bar date": last_date.isoformat(), "session_status": status,
        # components and raw inputs, kept for snapshots and replay
        "c_trend": parts["trend"], "c_rel": parts["rel"], "c_setup": parts["setup"],
        "c_volume": parts["volume"], "c_momentum": parts["momentum"],
        "inputs": {
            "price": c, "prev_close": prev_c, "open": float(last["Open"]), "high": hi, "low": lo, "volume": float(last["Volume"]),
            "sma20": sma20, "sma50": sma50, "sma20_prev": sma20_prev, "sma50_prev": sma50_prev,
            "atr": atr, "prior_high": ph, "prior_low": pl, "rsi": rsi, "d5": d5, "prev5": prev5,
            "vr": vr, "close_loc": close_loc, "rs_bench": rs_b, "bench": bname,
            "bench_above_sma50": B["above_sma50"] if B else None, "bench_sma50_rising": B["sma50_rising"] if B else None,
            "edays": edays,
        },
        "_rank": SETUP_RANK[setup],
    }


# ---------------------------------------------------------------------------
# Snapshots — one row per ticker per bar date per rules version per session status
# ---------------------------------------------------------------------------
SNAP_COLS = ["snapshot_key", "run_at", "rules_version", "engine_version", "source", "session_status",
             "bar_date", "ticker", "setup", "flags", "score", "alignment",
             "c_trend", "c_rel", "c_setup", "c_volume", "c_momentum"]
INPUT_COLS = ["price", "prev_close", "open", "high", "low", "volume", "sma20", "sma50", "sma20_prev", "sma50_prev",
              "atr", "prior_high", "prior_low", "rsi", "d5", "prev5", "vr", "close_loc", "rs_bench", "bench",
              "bench_above_sma50", "bench_sma50_rising", "edays"]


def write_snapshots(rows: list[dict], path: Path | str, source: str, run_at: datetime | None = None) -> int:
    """Append snapshots not already in the file. Returns the number written. Never rewrites existing rows."""
    path = Path(path)
    run_at = run_at or datetime.now()
    existing: set[str] = set()
    if path.exists():
        try:
            existing = set(pd.read_csv(path, usecols=["snapshot_key"])["snapshot_key"].astype(str))
        except Exception:
            existing = set()
    out = []
    for r in rows:
        key = f"{r['Ticker']}|{r['Bar date']}|{RULES_VERSION}|{r['session_status']}"
        if key in existing:
            continue
        existing.add(key)
        rec = {"snapshot_key": key, "run_at": run_at.isoformat(timespec="minutes"),
               "rules_version": RULES_VERSION, "engine_version": ENGINE_VERSION, "source": source,
               "session_status": r["session_status"], "bar_date": r["Bar date"], "ticker": r["Ticker"],
               "setup": r["Setup"], "flags": r["Flags"], "score": r["Breakout score"], "alignment": r["Alignment"],
               "c_trend": r["c_trend"], "c_rel": r["c_rel"], "c_setup": r["c_setup"],
               "c_volume": r["c_volume"], "c_momentum": r["c_momentum"]}
        for k in INPUT_COLS:
            rec["in_" + k] = r["inputs"].get(k)
        out.append(rec)
    if not out:
        return 0
    pd.DataFrame(out, columns=SNAP_COLS + ["in_" + k for k in INPUT_COLS]).to_csv(
        path, mode="a", index=False, header=not path.exists())
    return len(out)


# ---------------------------------------------------------------------------
# A full screen, with injectable fetch/earnings so it can run without a network
# ---------------------------------------------------------------------------
def run_screen(watchlist: list[str], fetch: Callable[[str], pd.DataFrame | None],
               earnings: Callable[[str], date | None], outdir: Path | str = ".",
               now: pd.Timestamp | None = None, snapshot_source: str = "yahoo") -> dict:
    outdir = Path(outdir)
    warnings: list[str] = []
    benches: dict[str, dict] = {}
    for b in BENCHMARKS:
        bdf = fetch(b)
        if bdf is None or len(bdf) < MIN_BARS:
            warnings.append(f"benchmark {b} unavailable; dependent scores withheld")
            continue
        cleaned, dropped = clean_bars(bdf)
        benches[b] = bench_series(cleaned)

    rows = []
    for t in watchlist:
        if t in BENCHMARKS:
            continue
        df = fetch(t)
        if df is None or len(df) < MIN_BARS:
            warnings.append(f"{t}: no data or fewer than {MIN_BARS} bars, skipped")
            continue
        r = analyze(t, df, benches, earnings(t), now)
        if r is None:
            warnings.append(f"{t}: not enough valid bars after cleaning, skipped")
            continue
        rows.append(r)

    if not rows:
        return {"rows": [], "warnings": warnings, "error": "No data for any ticker. Nothing written."}

    table = pd.DataFrame([{k: v for k, v in r.items() if k != "inputs"} for r in rows])
    table = table.sort_values(["_rank", "Breakout score"], ascending=[True, False], na_position="last")
    table = table.drop(columns="_rank").reset_index(drop=True)
    table.to_csv(outdir / "screener_results.csv", index=False)
    try:
        table.to_excel(outdir / "screener_results.xlsx", index=False)
    except Exception as e:  # openpyxl missing, etc.
        warnings.append(f"xlsx not written: {e}")
    written = write_snapshots(rows, outdir / "snapshots.csv", source=snapshot_source)
    return {"rows": rows, "table": table, "warnings": warnings, "error": None, "snapshots_written": written}
