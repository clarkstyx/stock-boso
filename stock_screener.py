"""
Short-Term Stock Screener
=========================
Pulls free daily price history from Yahoo Finance for a watchlist and ranks
each ticker on the metrics short-term / swing traders usually look at.

It does NOT tell you what to buy. It gives you the numbers so you can decide.

Run:
    pip install yfinance pandas openpyxl
    python stock_screener.py

Outputs:
    screener_results.csv
    screener_results.xlsx
    (and prints a ranked table to the terminal)
"""

import math
from datetime import datetime

import pandas as pd
import yfinance as yf

# ---------------------------------------------------------------------------
# 1. CONFIG — edit this watchlist to whatever you want to track
# ---------------------------------------------------------------------------
WATCHLIST = [
    # Semis / AI hardware
    "NVDA", "AMD", "AVGO", "TSM", "MU", "INTC", "ARM", "MRVL", "QCOM", "SMCI",
    # Big tech
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA",
    # Software / AI-adjacent
    "PLTR", "CRWD", "SNOW", "ORCL",
    # High-volatility retail favourites
    "COIN", "MSTR", "HOOD", "SOFI",
]

LOOKBACK_PERIOD = "6mo"   # how much history to pull
ATR_WINDOW = 14           # days for Average True Range
RSI_WINDOW = 14           # days for RSI
VOL_WINDOW = 20           # days for average volume


# ---------------------------------------------------------------------------
# 2. INDICATOR HELPERS
# ---------------------------------------------------------------------------
def rsi(close: pd.Series, window: int = 14) -> float:
    """Relative Strength Index. <30 = oversold, >70 = overbought (rough rule)."""
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss
    value = 100 - (100 / (1 + rs))
    return float(value.iloc[-1])


def atr_pct(df: pd.DataFrame, window: int = 14) -> float:
    """Average True Range as a % of price — how much it moves on a typical day."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    atr = true_range.rolling(window).mean().iloc[-1]
    return float(atr / close.iloc[-1] * 100)


# ---------------------------------------------------------------------------
# 3. SCREEN ONE TICKER
# ---------------------------------------------------------------------------
def analyze(ticker: str) -> dict | None:
    df = yf.download(ticker, period=LOOKBACK_PERIOD, progress=False, auto_adjust=True)
    if df.empty or len(df) < 60:
        print(f"  skipping {ticker}: not enough data")
        return None

    # yfinance sometimes returns multi-level columns; flatten them
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    close = df["Close"]
    last = float(close.iloc[-1])

    high_20 = float(df["High"].tail(20).max())
    low_20 = float(df["Low"].tail(20).min())
    high_52w = float(df["High"].max())
    low_52w = float(df["Low"].min())

    avg_vol = float(df["Volume"].tail(VOL_WINDOW).mean())
    today_vol = float(df["Volume"].iloc[-1])

    sma_20 = float(close.tail(20).mean())
    sma_50 = float(close.tail(50).mean())

    return {
        "Ticker": ticker,
        "Price": round(last, 2),
        "1d %": round((last / float(close.iloc[-2]) - 1) * 100, 2),
        "5d %": round((last / float(close.iloc[-6]) - 1) * 100, 2),
        "20d %": round((last / float(close.iloc[-21]) - 1) * 100, 2),
        # Volatility — bigger = bigger daily swings (more opportunity AND more risk)
        "ATR %": round(atr_pct(df, ATR_WINDOW), 2),
        # Momentum / stretch
        "RSI": round(rsi(close, RSI_WINDOW), 1),
        "vs SMA20 %": round((last / sma_20 - 1) * 100, 2),
        "vs SMA50 %": round((last / sma_50 - 1) * 100, 2),
        # Where it sits in its recent range (0 = at the low, 100 = at the high)
        "20d range pos": round((last - low_20) / (high_20 - low_20) * 100, 1)
        if high_20 != low_20 else 50.0,
        "From 6mo high %": round((last / high_52w - 1) * 100, 2),
        "From 6mo low %": round((last / low_52w - 1) * 100, 2),
        # Liquidity — can you get in/out easily? ($ traded per day, in millions)
        "Avg $Vol (M)": round(avg_vol * last / 1e6, 1),
        # Is something happening right now?
        "Vol vs avg": round(today_vol / avg_vol, 2) if avg_vol else math.nan,
    }


# ---------------------------------------------------------------------------
# 4. RUN THE SCREEN
# ---------------------------------------------------------------------------
def main() -> None:
    print(f"Screening {len(WATCHLIST)} tickers — {datetime.now():%Y-%m-%d %H:%M}\n")
    rows = [r for t in WATCHLIST if (r := analyze(t))]
    results = pd.DataFrame(rows)

    # Default sort: most volatile first (what scalpers care about most),
    # then most liquid. Change this to whatever matters to you.
    results = results.sort_values(["ATR %", "Avg $Vol (M)"], ascending=[False, False])
    results = results.reset_index(drop=True)

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)
    print(results.to_string(index=False))

    results.to_csv("screener_results.csv", index=False)
    results.to_excel("screener_results.xlsx", index=False)
    print("\nSaved screener_results.csv and screener_results.xlsx")

    # Quick, purely mechanical flags — not advice, just filters you can tweak
    print("\n--- Mechanical flags (tweak the thresholds in the code) ---")
    oversold = results[results["RSI"] < 35]
    overbought = results[results["RSI"] > 70]
    unusual_vol = results[results["Vol vs avg"] > 1.5]
    print("RSI < 35 (stretched down):   ", ", ".join(oversold["Ticker"]) or "none")
    print("RSI > 70 (stretched up):     ", ", ".join(overbought["Ticker"]) or "none")
    print("Volume > 1.5x 20d average:   ", ", ".join(unusual_vol["Ticker"]) or "none")


if __name__ == "__main__":
    main()
