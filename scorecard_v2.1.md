# Stock Boso — replay scorecard

Rules v2.1 · engine v2.1.1 · generated 2026-10-28 00:00  
Universe: NVDA, AMD, AVGO, TSM, MU, INTC, ARM, MRVL, QCOM, SMCI, AAPL, MSFT, GOOGL, AMZN, META, TSLA, PLTR, COIN, MSTR, HOOD (benchmarks QQQ, SMH)  
Bars: 2022-01-25 to 2026-10-13 (Yahoo, auto-adjusted). Signals stop 10 sessions before the end.  
Development period: up to 2025-10-13. Holdout (untouched): 2025-10-13 onward — SHOWN below.

**Read this first**

- This is research, not a trading signal. Past results do not predict future ones.
- **Survivorship bias:** the 20 names were picked in 2026, knowing they mattered. Absolute returns are flattered. The fair comparison is *between rankings on the same names and days*, which is what the verdict uses.
- Earnings dates are not known historically, so the Earnings flag never fires here.
- Costs: 0.2% per round trip on every trade. Each day's top 3 is treated as a fresh 5-day trade; real holding would overlap and trade less often.
- Comparisons run: 3 rankings × 4 horizons, plus setup and bucket tables. With that many looks, one 'good-looking' number by itself means little. Only the primary verdict line counts.

## Development period

**Verdict: the score does NOT beat RS-alone** — score − RS = -0.488% per trade-day (90% interval -0.841 to -0.146), P(>0) = 1%, ahead in 1 of 4 years.

Decision rule (agreed in advance): if the score does not beat RS-alone after costs with reasonable stability, drop the composite and keep the indicators.

### Headline: 5-session, executable (next open → close), net of 0.2% costs

932 trading days. 'vs bench' = return minus SMH/QQQ over the same dates. Win rate and win/loss are absolute (did the trade itself make money).

| Ranking | mean vs bench % | 90% interval | win rate | avg win % | avg loss % | large losses (≤-5%) | MAE median % | MAE worst 10% | mean at 2× costs |
|---|---|---|---|---|---|---|---|---|---|
| Top 3 by breakout score | -0.01 | -0.37 to +0.37 | 52% | +5.76 | -5.43 | 19.5% | -3.53 | -11.66 | -0.21 |
| Top 3 by RS vs bench | +0.48 | -0.07 to +1.06 | 53% | +7.46 | -6.27 | 22.5% | -4.26 | -13.38 | +0.28 |
| Top 3 by 5-day momentum | +0.46 | -0.02 to +0.98 | 52% | +7.13 | -5.93 | 21.8% | -4.28 | -12.94 | +0.26 |
| All eligible (equal weight) | +0.20 | -0.01 to +0.42 | 52% | +5.95 | -5.18 | 18.6% | -3.46 | -10.95 | +0.00 |

### Head to head at every horizon (score minus the alternative, executable, vs bench, net)

| Horizon | score − RS | P(>0) | score − momentum | P(>0) | score top-3, close→close (descriptive) |
|---|---|---|---|---|---|
| 1d | -0.095 | 3% | -0.085 | 6% | +0.094 |
| 3d | -0.335 | 0% | -0.356 | 1% | +0.174 |
| 5d (primary) | -0.488 | 1% | -0.471 | 2% | +0.292 |
| 10d | -0.804 | 1% | -0.982 | 0% | +0.602 |

### Does a higher number mean a better 5-day result? (rank IC)

Rank IC = how well each day's ordering matched the next 5 days' ordering. 0 = no relationship, +1 = perfect. Values around +0.05 are already considered useful in practice.

| Ranking key | mean IC | 90% interval | days with IC > 0 |
|---|---|---|---|
| score | -0.014 | -0.038 to +0.010 | 46% |
| rs | -0.002 | -0.030 to +0.026 | 48% |
| mom5 | -0.001 | -0.025 to +0.024 | 48% |

### By setup label (distinct episodes: the first day a ticker enters the setup)

| Setup | episodes | mean vs bench % | win rate | avg win % | avg loss % | large losses | MAE worst 10% |
|---|---|---|---|---|---|---|---|
| Breakout confirmed | 712 | +0.14 | 51% | +5.25 | -4.52 | 15.7% | -9.72 |
| Breakout watch | 1056 | +0.21 | 53% | +5.15 | -4.44 | 15.7% | -9.67 |
| Pullback watch | 607 | -0.02 | 50% | +5.57 | -5.23 | 18.5% | -10.85 |
| Downtrend | 592 | -0.08 | 48% | +6.23 | -5.61 | 23.5% | -13.00 |
| No setup | 1873 | +0.04 | 52% | +5.84 | -5.48 | 20.1% | -11.40 |

### By score bucket (all scored ticker-days)

| Bucket | ticker-days | mean vs bench % | win rate |
|---|---|---|---|
| Strong ≥75 | 1567 | +0.59 | 53% |
| Moderate 55–74 | 4194 | +0.24 | 54% |
| Mixed 35–54 | 3785 | -0.04 | 51% |
| Weak <35 | 8623 | +0.23 | 52% |

### Stability

| Period | days | score − RS % | score % | RS % |
|---|---|---|---|---|
| 2022 | 236 | -0.230 | -0.87 | -0.64 |
| 2023 | 250 | -0.864 | -0.22 | +0.64 |
| 2024 | 252 | -0.810 | +0.61 | +1.42 |
| 2025 | 194 | +0.101 | +0.51 | +0.41 |
| QQQ above its SMA50 | 620 | -0.697 | +0.28 | +0.97 |
| QQQ below its SMA50 | 312 | -0.073 | -0.58 | -0.51 |

## Holdout period (last 12 months, evaluated once)

**Verdict: the score does NOT beat RS-alone** — score − RS = -0.061% per trade-day (90% interval -0.534 to +0.417), P(>0) = 43%, ahead in 0 of 2 years.

Decision rule (agreed in advance): if the score does not beat RS-alone after costs with reasonable stability, drop the composite and keep the indicators.

### Headline: 5-session, executable (next open → close), net of 0.2% costs

252 trading days. 'vs bench' = return minus SMH/QQQ over the same dates. Win rate and win/loss are absolute (did the trade itself make money).

| Ranking | mean vs bench % | 90% interval | win rate | avg win % | avg loss % | large losses (≤-5%) | MAE median % | MAE worst 10% | mean at 2× costs |
|---|---|---|---|---|---|---|---|---|---|
| Top 3 by breakout score | -0.04 | -0.72 to +0.70 | 48% | +7.44 | -5.78 | 24.5% | -4.43 | -12.81 | -0.24 |
| Top 3 by RS vs bench | +0.02 | -0.78 to +0.85 | 49% | +8.26 | -6.27 | 25.9% | -4.85 | -13.76 | -0.18 |
| Top 3 by 5-day momentum | -0.23 | -1.01 to +0.59 | 47% | +7.91 | -6.11 | 26.6% | -4.75 | -13.56 | -0.43 |
| All eligible (equal weight) | -0.23 | -0.66 to +0.22 | 49% | +6.28 | -5.38 | 21.5% | -4.00 | -11.80 | -0.43 |

### Head to head at every horizon (score minus the alternative, executable, vs bench, net)

| Horizon | score − RS | P(>0) | score − momentum | P(>0) | score top-3, close→close (descriptive) |
|---|---|---|---|---|---|
| 1d | -0.020 | 42% | -0.011 | 47% | +0.127 |
| 3d | +0.023 | 56% | +0.205 | 84% | +0.235 |
| 5d (primary) | -0.061 | 43% | +0.195 | 71% | +0.294 |
| 10d | -0.484 | 13% | -0.196 | 36% | +0.170 |

### Does a higher number mean a better 5-day result? (rank IC)

Rank IC = how well each day's ordering matched the next 5 days' ordering. 0 = no relationship, +1 = perfect. Values around +0.05 are already considered useful in practice.

| Ranking key | mean IC | 90% interval | days with IC > 0 |
|---|---|---|---|
| score | -0.013 | -0.066 to +0.044 | 50% |
| rs | -0.016 | -0.069 to +0.040 | 48% |
| mom5 | -0.016 | -0.061 to +0.032 | 46% |

### By setup label (distinct episodes: the first day a ticker enters the setup)

| Setup | episodes | mean vs bench % | win rate | avg win % | avg loss % | large losses | MAE worst 10% |
|---|---|---|---|---|---|---|---|
| Breakout confirmed | 174 | -0.23 | 42% | +8.56 | -5.93 | 27.6% | -11.95 |
| Breakout watch | 244 | -0.38 | 45% | +7.09 | -5.92 | 30.3% | -12.29 |
| Pullback watch | 174 | -0.36 | 46% | +6.95 | -6.21 | 25.9% | -14.26 |
| Downtrend | 167 | +0.31 | 48% | +6.54 | -5.13 | 18.6% | -10.60 |
| No setup | 521 | -0.17 | 46% | +6.49 | -5.39 | 24.8% | -11.55 |

### By score bucket (all scored ticker-days)

| Bucket | ticker-days | mean vs bench % | win rate |
|---|---|---|---|
| Strong ≥75 | 377 | -0.13 | 45% |
| Moderate 55–74 | 1046 | -0.27 | 47% |
| Mixed 35–54 | 1106 | -0.27 | 49% |
| Weak <35 | 2511 | -0.21 | 51% |

### Stability

| Period | days | score − RS % | score % | RS % |
|---|---|---|---|---|
| 2025 | 56 | -0.047 | -1.01 | -0.97 |
| 2026 | 196 | -0.065 | +0.24 | +0.30 |
| QQQ above its SMA50 | 170 | -0.190 | +0.05 | +0.24 |
| QQQ below its SMA50 | 82 | +0.207 | -0.24 | -0.44 |
