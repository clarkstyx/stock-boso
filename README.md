# stock-boso

A swing-trading screener. It identifies and ranks trade setups, shows the evidence,
and flags risks. The trading decision stays with you. Not financial advice.

Two versions, same math:

- `stock_screener.py` — Python, free Yahoo Finance data, outputs CSV + XLSX + `history.csv`
- `index.html` — single web page, demo data by default, live quotes via a free Twelve Data key

## Quick start (Python)

```bash
pip install -r requirements.txt
python stock_screener.py
```

### Run it automatically (Windows)

Clone the repo, then double-click `setup_windows_task.bat` once. It installs the packages,
does a test run, and creates a scheduled task that runs the screener every weekday at
2:35 PM Regina time (4:35 PM ET, after the close). Results land in the same folder;
`history.csv` grows by one snapshot per day.

## Quick start (web)

Open `index.html` in a browser. Paste a Twelve Data API key (free at twelvedata.com) and
click **Run screen**. The free tier allows 8 credits/min, so 20 tickers + 2 benchmarks
takes about 3 minutes. Tick "Fetch earnings dates" to add those (1 extra credit per symbol).

## What it computes

| Column | What it means |
|---|---|
| Setup | Rule match, not a prediction: Breakout candidate / Pullback watch / Extended / Downtrend / No setup (rules below) |
| Breakout alignment | 0–100 score of how well the stock matches the momentum-breakout strategy today (buckets below). Not a probability. |
| Earnings | Days until the next earnings date. Flagged red within 7 days. Dates can be estimates; verify on investor relations. |
| RS vs QQQ / SMH | 20-day return minus the benchmark's 20-day return, in percentage points. Positive = leading, not just riding the index. |
| ATR % | 14-day Wilder ATR (includes overnight gaps) as % of price. Volatility, not direction. |
| RSI | 14-day Wilder RSI, matches TradingView. Over 70 is not an automatic sell in a strong trend. |
| vs SMA20 / SMA50 | Distance from the 20- and 50-day averages. |
| 20d range | 0 = at the 20-day low, 100 = at the 20-day high (intraday highs/lows). |
| Avg $Vol (M) | Mean of close × volume over the last 20 completed sessions. |
| Vol vs avg | Latest session volume vs the 20 sessions before it. Understated while the market is open. |

### Setup rules

- **Breakout candidate**: price > SMA20 > SMA50, SMA20 rising, price in the top 15% of its 20-day range and within 1 ATR of the 20-day high.
- **Pullback watch**: SMA20 > SMA50, price > SMA50, price within −1.5 to +0.5 ATR of SMA20, RSI 40–60.
- **Extended**: price more than 2.5 ATR above SMA20, or RSI > 75.
- **Downtrend**: price < SMA20 < SMA50.

### Breakout alignment score

Five buckets, grouped so correlated signals don't double count:

| Bucket | Max | Measures |
|---|---|---|
| Trend | 25 | Price vs SMA20 and SMA50, SMA20 rising |
| Relative strength | 25 | RS vs QQQ and SMH, full marks at +5 pts over each |
| Setup | 20 | Position in the 20-day range, within 1 ATR of the high, not extended |
| Volume | 15 | Relative volume (counts half on a down day) |
| Momentum | 15 | RSI zone, 5-day return, acceleration vs the 20-day pace |

75+ strong, 55–74 moderate, 35–54 mixed, under 35 weak. A 78 means the rules are well matched today, not that there is a 78% chance of a rise. Earnings risk is deliberately kept outside the score so a strong setup never hides it.

## History / forward tracking

Each run appends a snapshot (date, ticker, setup, key inputs) to `history.csv` (Python) or
browser storage (web, "Copy snapshot history" button). This is the raw material for later
checking whether the setups actually led anywhere.

## Roadmap

1. Forward-return scorecard: use `history.csv` to check whether high scores actually led to better 1/3/5/10-day outcomes than sorting by RS or momentum alone. If not, the score gets reworked or dropped.
2. Trend Pullback score as a second strategy.
3. Scalp mode (gap %, time-of-day relative volume, VWAP, opening range) — needs an intraday feed, not the free tier.

## Notes

- Daily data is delayed. Use a broker feed (e.g. IBKR) for entries.
- During market hours the latest daily bar is still changing; the page says so in its status bar.
- Needs at least 60 trading days of history per ticker; newer listings are skipped.
