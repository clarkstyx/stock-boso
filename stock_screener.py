"""
Stock Boso — swing screener
===========================
Pulls free daily price history from Yahoo Finance for a watchlist and ranks
each ticker on the metrics swing traders look at, plus:

  * Relative strength vs QQQ and SMH (20-day return minus the benchmark's)
  * Next earnings date and days until it (flagged when within 7 days)
  * A transparent setup label: Breakout candidate / Pullback watch / Extended / Downtrend / No setup
  * A daily snapshot appended to history.csv so forward returns can be measured later

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

# ---------------------------------------------------------------------------
# 1. CONFIG — edit the watchlist to whatever you want to track
# ---------------------------------------------------------------------------
WATCHLIST = [
    "NVDA", "AMD", "AVGO", "TSM", "MU", "INTC", "ARM", "MRVL", "QCOM", "SMCI",
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA",
    "PLTR", "COIN", "MSTR", "HOOD",
]
BENCHMARKS = ["QQQ", "SMH"]   # broad growth index, semiconductor ETF
LOOKBACK_PERIOD = "6mo"
EARNINGS_WARN_DAYS = 7
HISTORY_FILE = "history.csv"


# ---------------------------------------------------------------------------
# 2. INDICATORS — Wilder smoothing so values match TradingView
# ---------------------------------------------------------------------------
def rsi_wilder(close: pd.Series, n: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Wilder's smoothing is an EMA with alpha = 1/n
    avg_gain = gain.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    rs = avg_gain / avg_loss
    value = 100 - 100 / (1 + rs)
    return float(value.iloc[-1])


def atr_wilder(df: pd.DataFrame, n: int = 14) -> float:
    """True range includes the overnight gap against the previous close."""
    prev_close = df["Close"].shift(1)
    tr = pd.concat(
        [df["High"] - df["Low"], (df["High"] - prev_close).abs(), (df["Low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return float(tr.ewm(alpha=1 / n, min_periods=n, adjust=False).mean().iloc[-1])


def pct(a: float, b: float) -> float:
    return (a / b - 1) * 100


# ---------------------------------------------------------------------------
# 3. DATA
# ---------------------------------------------------------------------------
def download(ticker: str) -> pd.DataFrame | None:
    # auto_adjust is set explicitly so split/dividend handling is deliberate and consistent
    df = yf.download(ticker, period=LOOKBACK_PERIOD, progress=False, auto_adjust=True)
    if df.empty or len(df) < 60:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def next_earnings(ticker: str) -> date | None:
    """Best-effort next earnings date from Yahoo. Dates can be estimates — verify on investor relations."""
    try:
        cal = yf.Ticker(ticker).calendar
        dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
        if dates:
            today = date.today()
            future = sorted(d for d in dates if d >= today)
            return future[0] if future else None
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# 4. SETUP RULES — transparent, same as the web page
# ---------------------------------------------------------------------------
def setup_label(last, sma20, sma50, sma20_prev, atr, high20, low20, rsi) -> str:
    uptrend = last > sma20 > sma50 and sma20 > sma20_prev
    dist = (last - sma20) / atr                       # distance from SMA20 in ATR units
    range_pos = (last - low20) / (high20 - low20) if high20 != low20 else 0.5
    if dist > 2.5 or rsi > 75:
        return "Extended"
    if uptrend and range_pos >= 0.85 and (high20 - last) <= atr:
        return "Breakout candidate"
    if sma20 > sma50 and last > sma50 and -1.5 <= dist <= 0.5 and 40 <= rsi <= 60:
        return "Pullback watch"
    if last < sma20 < sma50:
        return "Downtrend"
    return "No setup"


# ---------------------------------------------------------------------------
# 5. ANALYZE ONE TICKER
# ---------------------------------------------------------------------------
def analyze(ticker: str, df: pd.DataFrame, bench_ret: dict[str, float], earnings: date | None) -> dict:
    close = df["Close"]
    last = float(close.iloc[-1])
    last_date = df.index[-1].date()

    high20, low20 = float(df["High"].tail(20).max()), float(df["Low"].tail(20).min())
    atr = atr_wilder(df)
    sma20, sma50 = float(close.tail(20).mean()), float(close.tail(50).mean())
    sma20_prev = float(close.iloc[-25:-5].mean())      # SMA20 five sessions ago, for slope
    rsi = rsi_wilder(close)
    d20 = pct(last, float(close.iloc[-21]))

    # Completed sessions only (the latest bar may be partial during market hours)
    completed = df.iloc[-21:-1]
    dollar_vol = float((completed["Close"] * completed["Volume"]).mean()) / 1e6
    base_vol = float(completed["Volume"].mean())

    edays = (earnings - last_date).days if earnings else None

    return {
        "Ticker": ticker,
        "Setup": setup_label(last, sma20, sma50, sma20_prev, atr, high20, low20, rsi),
        "Earnings in (d)": edays,
        "Earnings date": earnings.isoformat() if earnings else "",
        "Price": round(last, 2),
        "1d %": round(pct(last, float(close.iloc[-2])), 2),
        "5d %": round(pct(last, float(close.iloc[-6])), 2),
        "20d %": round(d20, 2),
        "RS vs QQQ": round(d20 - bench_ret["QQQ"], 2) if "QQQ" in bench_ret else None,
        "RS vs SMH": round(d20 - bench_ret["SMH"], 2) if "SMH" in bench_ret else None,
        "ATR %": round(atr / last * 100, 2),
        "RSI": round(rsi, 1),
        "vs SMA20 %": round(pct(last, sma20), 2),
        "vs SMA50 %": round(pct(last, sma50), 2),
        "20d range pos": round((last - low20) / (high20 - low20) * 100, 1) if high20 != low20 else 50.0,
        "From 6mo high %": round(pct(last, float(df["High"].max())), 2),
        "From 6mo low %": round(pct(last, float(df["Low"].min())), 2),
        "Avg $Vol (M)": round(dollar_vol, 1),
        "Vol vs avg": round(float(df["Volume"].iloc[-1]) / base_vol, 2) if base_vol else None,
        "Bar date": last_date.isoformat(),
    }


# ---------------------------------------------------------------------------
# 6. RUN
# ---------------------------------------------------------------------------
SETUP_ORDER = {"Breakout candidate": 0, "Pullback watch": 1, "Extended": 2, "Downtrend": 3, "No setup": 4}


def main() -> None:
    print(f"Stock Boso — {datetime.now():%Y-%m-%d %H:%M}\n")

    # Benchmarks first so relative strength can be computed
    bench_ret: dict[str, float] = {}
    for b in BENCHMARKS:
        bdf = download(b)
        if bdf is not None:
            bench_ret[b] = pct(float(bdf["Close"].iloc[-1]), float(bdf["Close"].iloc[-21]))
    print("Benchmark 20d returns:", {k: round(v, 2) for k, v in bench_ret.items()})

    rows = []
    for t in WATCHLIST:
        df = download(t)
        if df is None:
            print(f"  skipping {t}: not enough data")
            continue
        rows.append(analyze(t, df, bench_ret, next_earnings(t)))

    results = pd.DataFrame(rows)
    results["_order"] = results["Setup"].map(SETUP_ORDER)
    results = results.sort_values(["_order", "RS vs QQQ"], ascending=[True, False]).drop(columns="_order").reset_index(drop=True)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", None)
    print(results.to_string(index=False))

    results.to_csv("screener_results.csv", index=False)
    results.to_excel("screener_results.xlsx", index=False)

    # Snapshot for later forward-return measurement
    snap = results[["Bar date", "Ticker", "Setup", "Price", "RSI", "RS vs QQQ", "ATR %", "20d range pos", "Vol vs avg"]].copy()
    snap.insert(1, "Run at", datetime.now().isoformat(timespec="minutes"))
    snap.to_csv(HISTORY_FILE, mode="a", index=False, header=not os.path.exists(HISTORY_FILE))

    print("\nSaved screener_results.csv, screener_results.xlsx; appended history.csv")
    bar = results["Bar date"].iloc[0]
    print(f"Bars through {bar}. If that is today and the market is open, the latest bar is still changing.")

    print("\n--- Setups ---")
    for name in SETUP_ORDER:
        names = ", ".join(results.loc[results["Setup"] == name, "Ticker"]) or "none"
        print(f"{name:20s} {names}")
    soon = results[(results["Earnings in (d)"].notna()) & (results["Earnings in (d)"] >= 0) & (results["Earnings in (d)"] <= EARNINGS_WARN_DAYS)]
    print(f"{'Earnings <= 7d':20s} {', '.join(soon['Ticker']) or 'none'}")


if __name__ == "__main__":
    main()
