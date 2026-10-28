# Stock Boso — project context for Claude Code

Read this first. It is the handover from the claude.ai session that built the project (Oct 26–27, 2026).

## What this is

A swing-trading **screener**, not a signal service. It matches daily bars against written rules,
labels setups, flags risks, and shows a transparent 0–100 "breakout alignment" score with its five
components. It never says buy/sell. Owner: Clark Valencia (Valencia AI). Beginner programmer,
vibe-codes with AI; explain changes plainly and keep deliverables complete and copy-pasteable.

Rules are **frozen at v2.1**. Do not add indicators, change weights, or redesign the score. The whole
point of the next phase is to test whether v2.1 adds value; changing it first would invalidate that.

## Layout

| File | Role |
|---|---|
| `boso.py` | The engine. Pure logic, no network, no clock when `now=None`. Everything else calls this. |
| `stock_screener.py` | CLI. Yahoo Finance via yfinance → `boso.run_screen()` → CSV/XLSX + `snapshots.csv`. |
| `index.html` | Single-page web version. Same rules in JavaScript. Demo data by default; live via a Twelve Data key in the browser. Exports `window.StockBoso` for parity tests. Hosted on GitHub Pages. |
| `tests/` | 17 pytest cases incl. Python↔JS parity on `tests/fixtures/bars.json`. `pytest -q` must stay green. |
| `setup_windows_task.bat` | One-click Windows setup: installs deps, test run, schedules weekdays 15:35 Regina (after US close in EDT and EST). |
| `snapshots.csv` | **Research record.** One row per ticker per bar date per rules+engine version per session status. Append-only, idempotent, never rewrite. Gitignored. |
| `history.csv` | Old engine-v2 snapshot format. Leave untouched. |
| `README.md` | Full rule definitions, score buckets, changelog. Keep it in sync with any change. |

## Versions

- `RULES_VERSION = v2.1` — strategy. Frozen.
- `ENGINE_VERSION = v2.1.1` — calculations/data handling. Bump only for a demonstrated correctness fix,
  log it in README, and note that numbers may shift slightly. Snapshot keys include both versions.

## Invariants (tests enforce most of these)

- Prior 20-day high/low use t−20..t−1, excluding today's bar.
- Benchmark returns are aligned by **date** (`asof`), not position. One benchmark per ticker: SMH for
  `SEMIS`, QQQ otherwise. Missing benchmark → `Incomplete`, score withheld (never neutral points).
- RSI/ATR are Wilder, seeded with a 14-bar simple average (TradingView RMA). Python and JS must match
  within 0.5 per score component, labels exactly.
- Intraday (US market open on the latest bar's date): volume bucket is **n/a**, score is "Provisional
  (max 85)", heavy-selling flag waits for the close. A partial reading is never scored as bearish.
- `boso.analyze(..., now=None)` must never consult the clock (test 12). This is what the replay uses.
- Extended is a **flag**, not a score penalty. Earnings proximity is a flag, outside the score.
- Bad/NaN OHLC bars are dropped and the row is flagged; zero-movement series → `Invalid data`.

## Current state (as of Oct 27, 2026)

- First production run Oct 26 after the close: 20 tickers, all `final`, 20 snapshot rows, all scores
  reproducible from stored inputs (audited). TSLA was the only Breakout confirmed (83). Both QQQ and
  SMH were below falling SMA50s, so the RS bucket capped at 15/25 for everyone.
- Scheduled task "Stock Boso daily screen" on Clark's laptop runs from this repo folder
  (`D:\Projects\valencia-ai\stock-boso`), writing `last_run.log` and `snapshots.csv` here.
  **Verified** Oct 27: the 15:35 run fired (result 0), 20 new `final` rows, 41 lines total, no
  duplicate keys. TSLA still the only Breakout confirmed (80).
- **Open check**: NVDA RSI(14)/ATR(14) vs TradingView daily, to confirm Yahoo data matches. Within
  ~0.3 RSI / ~$0.10 ATR = fine. Not yet done.
- Yahoo's earnings calendar sometimes blanks right after a report (TSLA, META on Oct 26). A missing
  earnings badge ≠ no earnings risk; worth a one-line note on the page if not already there.
- Known limits: Twelve Data free tier (8 credits/min) throttles the web page; the Claude artifact copy
  of the page cannot fetch live data (sandbox), only the GitHub Pages copy can.

## Next milestone: historical replay engine (approved plan, not started)

Build `replay.py` on top of `boso.analyze(now=None)`:

1. Pull 3–5 years of daily bars per ticker + QQQ + SMH via yfinance (`auto_adjust=True`, explicit).
2. For each date t (after a 60-bar warm-up, stopping 10 sessions before the end), slice bars `[:t]`
   and benchmark series `[:t]`, call `analyze` with `earnings=None`, `now=None`. No lookahead: nothing
   from after t may be visible, including benchmark bars.
3. Record setup, flags, score, components, and forward returns at 1/3/5/10 sessions, computed
   **close→close** (descriptive) and **next-open→close+N** (executable) with a cost assumption
   (~0.1% round trip + slippage). Label the two clearly.
4. Count **distinct episodes**: the first day a ticker enters a setup, not every repeated day.
5. Scorecard, 5-session horizon primary, 1/3/10 as context:
   - top-3 by score vs top-3 by RS vs top-3 by 5-day momentum, same eligible universe and dates,
     benchmark-relative return, net of costs;
   - win rate, avg win/loss, max adverse excursion, large-loss frequency;
   - by setup label (Breakout confirmed / watch / Pullback / Downtrend / No setup);
   - stability across years and regimes; uncertainty via time-blocked resampling (overlapping windows).
6. Hold out an untouched evaluation period (e.g. the most recent 12 months). Do not tune on it.
7. Output: `replay_results.csv` + a readable `scorecard.md`. The decision rule, agreed in advance:
   if the score does not beat RS-alone ranking after costs with reasonable stability, drop the
   composite and keep the indicators. That is a successful experiment, not a failure.

Do NOT: optimize weights, add VCP/Bollinger/multi-horizon RS, scrape TradingView, or publish bulk
OHLCV data (data-rights issue). Those are explicitly deferred.

After the replay: a separate Trend Pullback score, then a conservative entry/stop/size calculator
(0.25–0.5% risk while learning, stop from chart structure, ATR as sanity check).

## Working conventions

- Run `pytest -q` before and after any change to `boso.py` or `index.html`'s analyze().
- Python and JS must change together; the parity test will catch drift.
- Commit messages describe behaviour, not files. Push to `main`; GitHub Pages redeploys automatically.
- The web page's `<title>` stays "Stock Boso"; header shows `rules vX · engine vY`.
- Disclaimer and "How to use" sections on the page are intentional; keep them.
