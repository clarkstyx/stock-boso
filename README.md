# stock-boso

A swing-trading screener. It labels trade setups, shows the evidence and flags risks.
It does not rank or score anything (see "Why there is no score" below). The trading
decision stays with you. Not financial advice.

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

## What it computes (rules v3.0)

| Column | What it means |
|---|---|
| Setup | One label per stock, a rule match, not a prediction: Breakout confirmed / Breakout watch / Pullback watch / Downtrend / No setup |
| Flags | Can coexist with any label: Extended, Heavy selling, Earnings (≤ 7 days), Incomplete (benchmark missing, RS unavailable) |
| RS vs bench | 20-day return minus the benchmark's (SMH for semiconductors, QQQ for everything else), in percentage points. |
| RSI | 14-day Wilder RSI. |
| ATR % | 14-day Wilder ATR (includes overnight gaps) as % of price. Volatility, not direction. |
| Vol vs avg | Latest session's volume against the 20 before it. Not shown while the market is open: a partial day is not a reading. |
| Earnings | Days until the next earnings date. Dates can be estimates; verify on investor relations. |
| Full view | distance to SMA20/50, position in the prior 20-day range, avg dollar volume, 1/5/20-day change, RS vs QQQ |

Rows are sorted by label and then alphabetically. **This is not a ranking.**

**Prior 20-day high/low** use sessions t−20 to t−1 and exclude today, so today's bar cannot be its own breakout level.

### Setup rules

- **Breakout confirmed**: close above the prior 20-day high; price > SMA20 > SMA50; SMA20 rising.
- **Breakout watch**: same trend; close within 1 ATR below the prior high and in the top 15% of the prior range. Nothing has triggered yet.
- **Pullback watch**: SMA20 > SMA50, SMA50 rising, price > SMA50, price within −1.5 to +0.5 ATR of SMA20, RSI 40–60, RS vs bench no worse than −1 ATR.
- **Downtrend**: price < SMA20 < SMA50.

### Flags

- **Extended**: more than 2.5 ATR above SMA20, or RSI > 75.
- **Heavy selling**: volume ≥ 1.5× average with a close in the bottom 40% of the day's range and below the prior close.

### Why there is no score (v3.0, Oct 28 2026)

Rules v2.1 had a 0–100 "breakout alignment" score built from five buckets (trend, relative
strength, setup, volume, momentum). It was frozen and then tested with `replay.py` on this
watchlist over Jan 2022–Oct 2026, with the last 12 months held out and opened once. Picking the
top 3 by score, buying at the next open and holding 5 sessions after 0.2% costs did **no better
than picking the top 3 by relative strength alone** (−0.49% per trade behind it in development,
−0.06% in the holdout), and in the holdout none of score, RS or momentum beat simply holding the
benchmark. The rule agreed before the test was: if the score can't beat RS alone, drop it. So it
was dropped. The full tables are in `scorecard_v2.1.md`; the code that produced them is git tag
`rules-v2.1`.

What remains is a filter: labels and flags that tell you which charts match a written pattern
today. They did not show a measurable edge either, so treat them as a reading aid, not a signal.
Adding indicators to "fix" this on a 20-name universe would be data mining; see Roadmap for
what an honest next test looks like.

### Changes from v2 to v2.1 (history; the score itself is gone in v3.0)

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

`scorecard.md` compares top-3 by RS vs top-3 by 5-day momentum vs all names on the same days,
with a time-blocked bootstrap (overlapping trades), rank IC, distinct-episode results per setup,
and stability by year and QQQ regime. Bars are cached in `replay_data/` and results in
`replay_results.csv`; both are gitignored (personal research copy of Yahoo data), as is the
regenerated `scorecard.md`.

**The v2.1 test (Oct 27–28, 2026)** is frozen in `scorecard_v2.1.md` and reproducible from git
tag `rules-v2.1`. Development period Jan 2022–Oct 2025: the score did **not** beat RS-alone,
−0.49% per 5-day trade vs bench (90% interval −0.84 to −0.15), behind in 3 of 4 years. Holdout
Oct 2025–Oct 2026, opened once: score −0.04%, RS +0.02%, momentum −0.23%, all names −0.23%;
every interval straddled zero and RS's development edge did not repeat. Breakout labels
underperformed Downtrend in the holdout. Rank IC ≈ 0 for all three. **On this universe with 5-day
holds, nothing tested has a measurable edge after costs.** The 20-name universe was chosen in 2026
(survivorship), so even these flat numbers are optimistic.

## Versions

- **rules** change only when the strategy changes (currently v3.0: labels and flags, no score.
  v2.1 was frozen, tested, and is kept as git tag `rules-v2.1`).
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
snapshots; incomplete benchmark flags the row and leaves RS empty; intraday hides the partial
volume reading and holds the heavy-selling flag until the close; no score, alignment or component
field anywhere in the output or the snapshot; breakout label just below / at / above the prior
high; and Python vs JavaScript parity on a shared fixture (labels and flags exact, RSI/ATR/RS/
volume within rounding).
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

1. ~~Historical replay engine~~ — built. ~~Test the v2.1 score~~ — done, score removed (v3.0).
2. Keep the live daily snapshots as a separate forward test; no trading on these labels as signals.
3. Conservative entry/stop/size calculator (0.25–0.5% risk, stop from chart structure, ATR as a
   sanity check). This is the part of the plan that protects money whether or not any signal works.
4. An honest second replay, decided in advance: a wider universe (not hand-picked survivors) and
   longer holds (20–60 sessions, where momentum has published evidence). No new indicators until
   that test design is written down.
5. Scalp mode (gap %, time-of-day relative volume, VWAP, opening range) — needs an intraday feed, not the free tier. Deferred.

## Notes

- Daily data is delayed. Use a broker feed (e.g. IBKR) for entries.
- During market hours the latest daily bar is still changing; the page says so in its status bar.
- Needs at least 60 trading days of history per ticker; newer listings are skipped.
