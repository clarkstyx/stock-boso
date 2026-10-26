# stock-boso

A simple short-term stock screener. Pulls free daily price history from Yahoo Finance
for a watchlist and ranks each ticker on the metrics swing / short-term traders look at.

It does **not** tell you what to buy. It gives you the numbers so you can decide.
Not financial advice.

## Quick start

```bash
pip install -r requirements.txt
python stock_screener.py
```

Prints a ranked table and saves `screener_results.csv` and `screener_results.xlsx`.

## Columns

| Column | What it means |
|---|---|
| ATR % | Typical daily swing as % of price. Higher = more movement (more opportunity and more risk). |
| Avg $Vol (M) | Dollars traded per day. Higher = tighter spreads, easier to get in and out. |
| RSI | < 35 = beaten down recently, > 70 = stretched up. A condition, not a prediction. |
| vs SMA20 / SMA50 % | How far price is above/below its 20- and 50-day averages. |
| 20d range pos | 0 = at the 20-day low, 100 = at the 20-day high. |
| From 6mo high/low % | Distance from the 6-month extremes. |
| Vol vs avg | Today's volume vs the 20-day average. > 1.5 = something is happening. |

## Customizing

- Edit `WATCHLIST` at the top of `stock_screener.py` to track different tickers.
- Change the sort in `main()` (default: most volatile first, then most liquid).
- Tweak the flag thresholds at the bottom of `main()`.

## Notes

- Yahoo Finance data is delayed ~15 minutes. Use a live broker feed (e.g. IBKR) for actual entries.
- Needs at least ~60 trading days of history per ticker; newer listings are skipped.
