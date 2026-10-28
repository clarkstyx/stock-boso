"""
Stock Boso — command-line screener
==================================
Downloads daily bars from Yahoo Finance and runs the rules in boso.py.

    pip install -r requirements.txt
    python stock_screener.py

Outputs (in this folder):
    screener_results.csv / .xlsx   today's table
    snapshots.csv                  one row per ticker per completed session, never rewritten
    (history.csv from engine v2 is left untouched)

It does NOT tell you what to buy. Not financial advice.
"""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import yfinance as yf

import boso

# ---------------------------------------------------------------------------
# CONFIG — edit the watchlist to whatever you want to track
# ---------------------------------------------------------------------------
WATCHLIST = [
    "NVDA", "AMD", "AVGO", "TSM", "MU", "INTC", "ARM", "MRVL", "QCOM", "SMCI",
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA",
    "PLTR", "COIN", "MSTR", "HOOD",
]
LOOKBACK_PERIOD = "6mo"


def fetch(ticker: str) -> pd.DataFrame | None:
    # auto_adjust is set explicitly so split/dividend handling is deliberate and consistent
    try:
        df = yf.download(ticker, period=LOOKBACK_PERIOD, progress=False, auto_adjust=True)
    except Exception as e:
        print(f"  {ticker}: download failed ({e})")
        return None
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def next_earnings(ticker: str) -> date | None:
    """Best-effort next earnings date from Yahoo. May be an estimate; verify on investor relations."""
    try:
        cal = yf.Ticker(ticker).calendar
        dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
        if dates:
            future = sorted(d for d in dates if d >= date.today())
            return future[0] if future else None
    except Exception:
        pass
    return None


def main() -> None:
    print(f"Stock Boso — rules {boso.RULES_VERSION}, engine {boso.ENGINE_VERSION} — {datetime.now():%Y-%m-%d %H:%M}\n")
    now = pd.Timestamp.now(tz="America/New_York")
    out = boso.run_screen(WATCHLIST, fetch=fetch, earnings=next_earnings, outdir=".", now=now)

    for w in out["warnings"]:
        print("warning:", w)
    if out["error"]:
        print("\n" + out["error"])
        return

    table = out["table"]
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", None)
    compact = ["Ticker", "Setup", "Flags", "RS vs bench", "Bench", "RSI", "ATR %", "Vol vs avg", "Earnings in (d)", "Price", "Bar date", "session_status"]
    print(table[compact].to_string(index=False))

    status = table["session_status"].iloc[0]
    print(f"\nSaved screener_results.csv/.xlsx; {out['snapshots_written']} new snapshot rows in snapshots.csv")
    print(f"Bars through {table['Bar date'].iloc[0]} ({status}).", "Intraday: volume n/a, heavy-selling flag waits for the close." if status == "intraday" else "")
    print("Labels are rule matches to help you read a chart, not a ranking. See README: 'Why there is no score'.")

    print("\n--- Setups ---")
    for name in boso.SETUP_RANK:
        print(f"{name:20s} {', '.join(table.loc[table['Setup'] == name, 'Ticker']) or 'none'}")
    print("\n--- Flags ---")
    for flag in ["Extended", "Heavy selling", "Earnings", "Incomplete", "Invalid data"]:
        hit = table[table["Flags"].str.contains(flag, na=False)]
        print(f"{flag:20s} {', '.join(hit['Ticker']) or 'none'}")


if __name__ == "__main__":
    main()
