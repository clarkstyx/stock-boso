"""
Stock Boso — swing screener (rules v2.1)
========================================
Pulls free daily price history from Yahoo Finance for a watchlist and ranks
each ticker on the metrics swing traders look at. Same rules as index.html.

  * One benchmark per ticker (SMH for semiconductors, QQQ for everything else)
  * Relative strength vs that benchmark, in ATR units inside the score
  * Next earnings date, flagged when within 7 days (kept OUT of the score)
  * One setup label: Breakout confirmed / Breakout watch / Pullback watch / Downtrend / No setup
  * Flags that can coexist with any label: Extended, Heavy selling, Earnings, Incomplete
  * Breakout alignment score 0-100 in five buckets. NOT a probability.
  * A daily snapshot appended to history.csv, stamped with the rules version

It does NOT tell you what to buy. It gives you the numbers so you can decide.

Run:
    pip install -r requirements.txt
    python stock_screener.py

Outputs:
    screener_results.csv, screener_results.xlsx, history.csv (appended each run)
"""

from __future__ import annotations

import os
from datetime import date, datetime

import pandas as pd
import yfinance as yf

RULES_VERSION = "v2.1"

# ---------------------------------------------------------------------------
# 1. CONFIG — edit the watchlist to whatever you want to track
# ---------------------------------------------------------------------------
WATCHLIST = [
    "NVDA", "AMD", "AVGO", "TSM", "MU", "INTC", "ARM", "MRVL", "QCOM", "SMCI",
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA",
    "PLTR", "COIN", "MSTR", "HOOD",
]
BENCHMARKS = ["QQQ", "SMH"]
SEMIS = {"NVDA", "AMD", "AVGO", "TSM", "MU", "INTC", "ARM", "MRVL", "QCOM", "SMCI",
         "TXN", "ADI", "LRCX", "AMAT", "KLAC", "ASML", "ON", "MCHP", "NXPI", "MPWR"}
LOOKBACK_PERIOD = "6mo"
EARNINGS_WARN_DAYS = 7
HISTORY_FILE = "history.csv"


def bench_for(ticker: str) -> str:
    return "SMH" if ticker in SEMIS else "QQQ"


# ---------------------------------------------------------------------------
# 2. INDICATORS — Wilder smoothing so values match TradingView
# ---------------------------------------------------------------------------
def rsi_wilder(close: pd.Series, n: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    rs = avg_gain / avg_loss
    return float((100 - 100 / (1 + rs)).iloc[-1])


def atr_wilder(df: pd.DataFrame, n: int = 14) -> float:
    prev_close = df["Close"].shift(1)
    tr = pd.concat(
        [df["High"] - df["Low"], (df["High"] - prev_close).abs(), (df["Low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return float(tr.ewm(alpha=1 / n, min_periods=n, adjust=False).mean().iloc[-1])


def pct(a: float, b: float) -> float:
    return (a / b - 1) * 100


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def ramp(x: float, x0: float, x1: float) -> float:
    """0 at x0, 1 at x1, linear between, clamped."""
    return clamp((x - x0) / (x1 - x0), 0, 1)


# ---------------------------------------------------------------------------
# 3. DATA
# ---------------------------------------------------------------------------
def download(ticker: str, period: str = LOOKBACK_PERIOD) -> pd.DataFrame | None:
    df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
    if df.empty or len(df) < 61:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def next_earnings(ticker: str) -> date | None:
    """Best-effort next earnings date from Yahoo. May be an estimate — verify on investor relations."""
    try:
        cal = yf.Ticker(ticker).calendar
        dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
        if dates:
            future = sorted(d for d in dates if d >= date.today())
            return future[0] if future else None
    except Exception:
        pass
    return None


def bench_info(df: pd.DataFrame) -> dict:
    close = df["Close"]
    sma50 = float(close.tail(50).mean())
    sma50_prev = float(close.iloc[-60:-10].mean())
    return {
        "d20": pct(float(close.iloc[-1]), float(close.iloc[-21])),
        "above_sma50": float(close.iloc[-1]) > sma50,
        "sma50_rising": sma50 > sma50_prev,
    }


# ---------------------------------------------------------------------------
# 4. ANALYZE ONE TICKER — rules v2.1 (mirror of index.html)
# ---------------------------------------------------------------------------
def analyze(ticker: str, df: pd.DataFrame, benches: dict[str, dict], earnings: date | None) -> dict:
    close = df["Close"]
    last = df.iloc[-1]
    c, prev_c = float(last["Close"]), float(close.iloc[-2])
    last_date = df.index[-1].date()

    prior = df.iloc[-21:-1]                                   # t-20 .. t-1, excludes today
    ph, pl = float(prior["High"].max()), float(prior["Low"].min())
    atr = atr_wilder(df)
    atr_pct = atr / c * 100
    sma20, sma50 = float(close.tail(20).mean()), float(close.tail(50).mean())
    sma20_prev, sma50_prev = float(close.iloc[-25:-5].mean()), float(close.iloc[-60:-10].mean())
    completed = df.iloc[-21:-1]
    dollar_vol = float((completed["Close"] * completed["Volume"]).mean()) / 1e6
    base_vol = float(completed["Volume"].mean())
    vr = float(last["Volume"]) / base_vol if base_vol else 0.0
    hi, lo = float(last["High"]), float(last["Low"])
    close_loc = (c - lo) / (hi - lo) if hi > lo else 0.5
    d1, d5, d20 = pct(c, prev_c), pct(c, float(close.iloc[-6])), pct(c, float(close.iloc[-21]))
    prev5 = pct(float(close.iloc[-6]), float(close.iloc[-11]))
    rsi = rsi_wilder(close)

    bname = bench_for(ticker)
    B, BQ = benches.get(bname), benches.get("QQQ")
    rs_b = d20 - B["d20"] if B else None
    rs_q = d20 - BQ["d20"] if BQ else None
    rs_norm = rs_b / atr_pct if rs_b is not None else None
    edays = (earnings - last_date).days if earnings else None
    range_pos = 0.5 if ph == pl else (c - pl) / (ph - pl)
    dist_sma20 = (c - sma20) / atr

    # ----- label (one) -----
    up = c > sma20 > sma50 and sma20 > sma20_prev
    if up and c > ph:
        setup, rank = "Breakout confirmed", 0
    elif up and (ph - c) <= atr and range_pos >= 0.85:
        setup, rank = "Breakout watch", 1
    elif (sma20 > sma50 and sma50 > sma50_prev and c > sma50 and -1.5 <= dist_sma20 <= 0.5
          and 40 <= rsi <= 60 and (rs_norm is None or rs_norm >= -1)):
        setup, rank = "Pullback watch", 2
    elif c < sma20 < sma50:
        setup, rank = "Downtrend", 4
    else:
        setup, rank = "No setup", 5

    # ----- flags (any number) -----
    flags = []
    if dist_sma20 > 2.5 or rsi > 75:
        flags.append("Extended")
    if vr >= 1.5 and close_loc < 0.4 and c < prev_c:
        flags.append("Heavy selling")
    if edays is not None and 0 <= edays <= EARNINGS_WARN_DAYS:
        flags.append("Earnings")
    if rs_b is None:
        flags.append("Incomplete")

    # ----- breakout alignment score, five buckets. NOT a probability. -----
    vol_confirm = close_loc >= 0.5 and c >= prev_c
    parts = {
        "Trend": (8 if c > sma20 else 0) + (8 if sma20 > sma50 else 0)
                 + (5 if sma20 > sma20_prev else 0) + (4 if sma50 > sma50_prev else 0),
        "RelStrength": None if rs_norm is None else
                       ramp(rs_norm, 0, 2.5) * 15 + (6 if B["above_sma50"] else 0) + (4 if B["sma50_rising"] else 0),
        "Setup": ramp(range_pos, 0.6, 1) * 10 + (5 if ph - c <= atr else 0) + (5 if c > ph else 0),
        "Volume": ramp(vr, 0.8, 2) * 15 if vol_confirm else 0,
        "Momentum": (0 if rsi < 40 else ramp(rsi, 40, 55) * 8 if rsi < 55 else 8 if rsi <= 68
                     else (1 - ramp(rsi, 68, 78)) * 8 if rsi < 78 else 0)
                    + (4 if d5 > 0 else 0) + (3 if d5 > prev5 and d5 > 0 else 0),
    }
    if parts["RelStrength"] is None:
        score, align = None, "Incomplete"
    else:
        score = round(sum(parts.values()))
        align = ("Strong alignment" if score >= 75 else "Moderate alignment" if score >= 55
                 else "Mixed signals" if score >= 35 else "Weak alignment")

    return {
        "Ticker": ticker,
        "Setup": setup,
        "Flags": "|".join(flags),
        "Breakout score": score,
        "Alignment": align,
        "Score breakdown": " · ".join(f"{k} {('n/a' if v is None else f'{v:.0f}')}" for k, v in parts.items()),
        "Bench": bname,
        "RS vs bench": None if rs_b is None else round(rs_b, 2),
        "RS vs QQQ": None if rs_q is None else round(rs_q, 2),
        "Earnings in (d)": edays,
        "Earnings date": earnings.isoformat() if earnings else "",
        "Price": round(c, 2),
        "1d %": round(d1, 2), "5d %": round(d5, 2), "20d %": round(d20, 2),
        "ATR %": round(atr_pct, 2),
        "RSI": round(rsi, 1),
        "vs SMA20 %": round(pct(c, sma20), 2), "vs SMA50 %": round(pct(c, sma50), 2),
        "Prior 20d range pos": round(range_pos * 100, 1),
        "Prior 20d high": round(ph, 2),
        "Avg $Vol (M)": round(dollar_vol, 1),
        "Vol vs avg": round(vr, 2),
        "Bar date": last_date.isoformat(),
        "_rank": rank,
    }


# ---------------------------------------------------------------------------
# 5. RUN
# ---------------------------------------------------------------------------
def main() -> None:
    print(f"Stock Boso rules {RULES_VERSION} — {datetime.now():%Y-%m-%d %H:%M}\n")

    benches: dict[str, dict] = {}
    for b in BENCHMARKS:
        bdf = download(b)
        if bdf is not None:
            benches[b] = bench_info(bdf)
    print("Benchmarks:", {k: {"20d": round(v["d20"], 2), "above SMA50": v["above_sma50"], "SMA50 rising": v["sma50_rising"]} for k, v in benches.items()})

    rows = []
    for t in WATCHLIST:
        df = download(t)
        if df is None:
            print(f"  skipping {t}: not enough data")
            continue
        rows.append(analyze(t, df, benches, next_earnings(t)))

    results = pd.DataFrame(rows)
    results = results.sort_values(["_rank", "Breakout score"], ascending=[True, False], na_position="last")
    results = results.drop(columns="_rank").reset_index(drop=True)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", None)
    compact = ["Ticker", "Setup", "Flags", "Breakout score", "Alignment", "RS vs bench", "Bench", "ATR %", "Earnings in (d)", "Price", "Bar date"]
    print(results[compact].to_string(index=False))

    results.to_csv("screener_results.csv", index=False)
    results.to_excel("screener_results.xlsx", index=False)

    # Snapshot, one row per ticker per run, stamped with the rules version
    snap = results[["Bar date", "Ticker", "Setup", "Flags", "Breakout score", "Price", "RSI", "RS vs bench", "Bench", "ATR %", "Prior 20d range pos", "Vol vs avg"]].copy()
    snap.insert(1, "Run at", datetime.now().isoformat(timespec="minutes"))
    snap.insert(2, "Rules", RULES_VERSION)
    snap.to_csv(HISTORY_FILE, mode="a", index=False, header=not os.path.exists(HISTORY_FILE))

    print("\nSaved screener_results.csv, screener_results.xlsx; appended history.csv")
    print(f"Bars through {results['Bar date'].iloc[0]}. If that is today and the market is open, the latest bar is still changing.")

    print("\n--- Setups ---")
    for name in ["Breakout confirmed", "Breakout watch", "Pullback watch", "Downtrend", "No setup"]:
        print(f"{name:20s} {', '.join(results.loc[results['Setup'] == name, 'Ticker']) or 'none'}")
    print("\n--- Flags ---")
    for flag in ["Extended", "Heavy selling", "Earnings", "Incomplete"]:
        hit = results[results["Flags"].str.contains(flag, na=False)]
        print(f"{flag:20s} {', '.join(hit['Ticker']) or 'none'}")


if __name__ == "__main__":
    main()
