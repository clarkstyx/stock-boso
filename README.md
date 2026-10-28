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
3:35 PM Regina time (5:35 PM ET in summer, 4:35 PM ET in winter: after the close all year).
Results land in the same folder; `snapshots.csv` grows by one row per ticker per session.

If you set this up before engine v2.1.1, re-run the .bat once: it replaces the old 2:35 PM task.

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

## Snapshots / forward tracking

Each run appends to `snapshots.csv` (Python) or browser storage (web, "Copy snapshot history").
One row per ticker per bar date per rules version per session status; a repeat run adds nothing.
Rows carry the rules and engine versions, source, `final` vs `intraday`, the setup, flags, score,
all five score components and the raw inputs needed to recompute the score. Existing rows are
never rewritten. The `history.csv` from engine v2 is left as it was.

## Historical replay

```bash
python replay.py              # development period; the last 12 months stay hidden
python replay.py --holdout    # evaluate the holdout too: once, at the very end
```

For every past session t it slices the stock **and** benchmark bars to t, runs `boso.analyze`
with the same ~6-month window the live screener uses (`earnings=None`, `now=None`), and records
what happened next at 1/3/5/10 sessions:

- `cc_N` close→close, **descriptive** (you could not buy at that close);
- `ex_net_N` next open→close+N minus 0.2% round-trip cost, **executable**;
- `rel_*` the same minus the benchmark (SMH/QQQ) over the stock's own dates; `mae_N` worst low while held.

`scorecard.md` compares top-3 by score vs top-3 by RS vs top-3 by 5-day momentum on the same names
and days, with a time-blocked bootstrap (overlapping trades), rank IC, distinct-episode results per
setup, score buckets, and stability by year and QQQ regime. The pass/fail rule is written in
`replay.verdict()` and was fixed before the first run. Bars are cached in `replay_data/` and results
in `replay_results.csv`; both are gitignored (personal research copy of Yahoo data).

**Result (Oct 27–28, 2026).** Development period Jan 2022–Oct 2025: the score does **not** beat
RS-alone, −0.49% per 5-day trade vs bench (90% interval −0.84 to −0.15), behind in 3 of 4 years.
Holdout Oct 2025–Oct 2026, opened once: score −0.04%, RS +0.02%, momentum −0.23%, all names
−0.23%; every interval straddles zero and RS's development edge did not repeat. Breakout labels
underperformed Downtrend in the holdout. Rank IC ≈ 0 for all three. **Conclusion: on this
universe with 5-day holds, none of the rankings has a measurable edge after costs.** Per the
agreed rule the composite score is dropped as a ranking signal; the indicators and labels stay as
chart-reading aids only. The 20-name universe was chosen in 2026 (survivorship), so even these
flat numbers are optimistic.

## Versions

- **rules** change only when the strategy changes (currently v2.1, frozen for validation).
- **engine** changes when a calculation or data-handling defect is fixed (currently v2.1.1).
  Fixes can move numbers slightly; older snapshots keep their version stamp.

## Tests

```bash
pip install pytest
python tests/make_fixture.py   # only if tests/fixtures/bars.json is missing
pytest -q
```

Covers: benchmark returns aligned by date when a stock misses a session; flat and rising-only
series (no NaN); RSI seeded like TradingView's RMA; bad OHLC bars dropped and flagged; all
downloads failing gives a clear error and writes nothing; repeated runs add no duplicate
snapshots; incomplete benchmark withholds the score; intraday marks volume n/a and the score
provisional (never lower); breakout label just below / at / above the prior high; and
Python vs JavaScript parity on a shared fixture (labels exact, components within 0.5).
Replay (`tests/test_replay.py`): changing any bar after t, stock or benchmark, leaves day t
unchanged (lookahead guard); a replay row equals a direct `analyze` call; hand-computed forward
returns, benchmark legs aligned by date; distinct episodes; same eligible universe for every
ranking; deterministic bootstrap; 12-month holdout split.

### Engine v2.1.1 changes (no rules changes)

- Benchmark returns are aligned by date; a stock missing a session no longer shifts the window.
- RSI and ATR seed with a 14-bar simple average (TradingView RMA); Python and JavaScript now match.
- Bars with missing or impossible OHLC are dropped and the row is flagged; zero-movement series
  are flagged "Invalid data" with the score withheld instead of dividing by zero.
- While the US session is open, the volume bucket is n/a and the score is provisional out of 85.
  A partial reading is not a bearish signal. Heavy-selling flag also waits for the close.
- Snapshot format v2 as above; `history.csv` untouched.
- Python logic lives in `boso.py` (no network) so tests can run it; `stock_screener.py` is the CLI.
- Scheduled task moved to 3:35 PM Regina so it stays after the close through daylight-saving changes.

## Roadmap

1. ~~Historical replay engine~~ — built (`replay.py`, see above). First result: the score does not beat RS alone on the development period. Holdout still unopened.
2. Keep the live daily snapshots as a separate forward test; no trading during the observation period.
3. Trend Pullback score as a second strategy; conservative entry/stop/size calculator.
4. Scalp mode (gap %, time-of-day relative volume, VWAP, opening range) — needs an intraday feed, not the free tier.

## Notes

- Daily data is delayed. Use a broker feed (e.g. IBKR) for entries.
- During market hours the latest daily bar is still changing; the page says so in its status bar.
- Needs at least 60 trading days of history per ticker; newer listings are skipped.
