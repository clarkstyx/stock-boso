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

## What it computes (rules v2.1)

| Column | What it means |
|---|---|
| Setup | One label per stock, a rule match, not a prediction: Breakout confirmed / Breakout watch / Pullback watch / Downtrend / No setup |
| Flags | Can coexist with any label: Extended, Heavy selling, Earnings (≤ 7 days), Incomplete (benchmark missing, score withheld) |
| Breakout alignment | 0–100 score of how well the stock matches the momentum-breakout strategy today. Not a probability. Shown next to pullback labels for context only. |
| RS vs bench | 20-day return minus the benchmark's (SMH for semiconductors, QQQ for everything else), in percentage points. |
| ATR % | 14-day Wilder ATR (includes overnight gaps) as % of price. Volatility, not direction. |
| Earnings | Days until the next earnings date. Dates can be estimates; verify on investor relations. Deliberately outside the score. |
| Full view | RSI (Wilder 14), distance to SMA20/50, position in the prior 20-day range, avg dollar volume, volume vs average |

**Prior 20-day high/low** use sessions t−20 to t−1 and exclude today, so today's bar cannot be its own breakout level.

### Setup rules

- **Breakout confirmed**: close above the prior 20-day high; price > SMA20 > SMA50; SMA20 rising.
- **Breakout watch**: same trend; close within 1 ATR below the prior high and in the top 15% of the prior range. Nothing has triggered yet.
- **Pullback watch**: SMA20 > SMA50, SMA50 rising, price > SMA50, price within −1.5 to +0.5 ATR of SMA20, RSI 40–60, RS vs bench no worse than −1 ATR.
- **Downtrend**: price < SMA20 < SMA50.

### Flags

- **Extended**: more than 2.5 ATR above SMA20, or RSI > 75.
- **Heavy selling**: volume ≥ 1.5× average with a close in the bottom 40% of the day's range and below the prior close.

### Breakout alignment score

| Bucket | Max | Measures |
|---|---|---|
| Trend | 25 | Price > SMA20 (8), SMA20 > SMA50 (8), SMA20 rising (5), SMA50 rising (4) |
| Relative strength | 25 | RS vs bench in ATR units, full 15 at 2.5 ATR; benchmark regime 10: above its SMA50 (6), that SMA50 rising (4). Missing benchmark → score withheld. |
| Setup | 20 | Position in the prior range 60%→100% (0→10), within 1 ATR of the prior high (5), closed above it (5) |
| Volume | 15 | Relative volume 0.8×→2.0× (0→15), only if the close is in the upper half of the day's range and above the prior close; otherwise 0 |
| Momentum | 15 | RSI ramps 40→55 (0→8), flat 55–68, ramps 68→78 (8→0); last 5 days positive (4); last 5 days stronger than the 5 before and positive (3) |

75+ strong, 55–74 moderate, 35–54 mixed, under 35 weak. An 80 means the rules are well matched today, not that there is an 80% chance of a rise.

### Changes from v2 (after review)

- Relative strength no longer counts QQQ and SMH twice; one benchmark per ticker, volatility-normalized, plus a benchmark-regime term.
- Missing benchmark data withholds the score instead of awarding neutral points.
- Momentum acceleration compares two non-overlapping 5-day windows and requires the recent one to be positive (the old `5d > 20d/4` rewarded a slowing decline).
- Volume points require a confirming close instead of being halved on down days; heavy-volume selling is a separate flag.
- "Breakout" split into watch (near the level) and confirmed (closed above it); the level excludes today's bar.
- Extended is a flag, not a label, so it can't be hidden by a setup label.
- Pullback rule requires a rising SMA50 and non-weak relative strength.
- Trend bucket replaces the redundant price > SMA50 with SMA50 slope; RSI scoring is a ramp, not a cliff.
- Beginner checklist: 0.25–0.5% risk while learning, stop from chart structure (ATR as a sanity check), correlated-exposure question, stop orders don't guarantee the fill.

## History / forward tracking

Each run appends a snapshot (date, ticker, setup, key inputs) to `history.csv` (Python) or
browser storage (web, "Copy snapshot history" button). This is the raw material for later
checking whether the setups actually led anywhere.

## Roadmap

1. Historical replay engine (Python, 3–5 years of bars): run the frozen v2.1 rules on every past date, entry at the next open with a cost assumption, count distinct episodes, and produce the scorecard: 5-day benchmark-relative return for top-3 by score vs top-3 by RS vs by 5-day momentum on the same eligible universe; max adverse excursion; stability across periods. If the score can't beat RS alone, it goes and the indicators stay.
2. Keep the live daily snapshots as a separate forward test; no trading during the observation period.
3. Trend Pullback score as a second strategy; conservative entry/stop/size calculator.
4. Scalp mode (gap %, time-of-day relative volume, VWAP, opening range) — needs an intraday feed, not the free tier.

## Notes

- Daily data is delayed. Use a broker feed (e.g. IBKR) for entries.
- During market hours the latest daily bar is still changing; the page says so in its status bar.
- Needs at least 60 trading days of history per ticker; newer listings are skipped.
