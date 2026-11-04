# Challenger: TimesFM 2.5 (zero-shot)

Same 12 origins (2023Q2 to 2026Q1), horizons 1-4, targets up to 2026Q2, same metrics.
Checkpoint `google/timesfm-2.5-200m-pytorch` (Apache-2.0), used zero-shot on each series' own history. TimesFM's quantile
head gives the 10th-90th percentiles, so only 80% coverage is reported. For BottomUp, interval sums are
not valid, so no coverage is shown.

| model | method | mean_mase | mean_wape | coverage_80 | total_wape | total_mase |
|---|---|---:|---:|---|---:|---:|
| AutoARIMA_log | BottomUp | 0.490 | 6.6% | 93.2% | 3.2% | 0.333 |
| TimesFM-2.5 | BottomUp | 0.709 | 8.7% |  | 5.9% | 0.607 |
| TimesFM-2.5 | base | 0.744 | 9.0% | 60.7% | 7.3% | 0.761 |
| SeasonalNaive | base | 1.291 | 15.0% | 70.2% | 14.0% | 1.440 |

Lowest mean MASE: **AutoARIMA_log / BottomUp** (0.490).
The production model was **not** changed: it was selected by the rule in `backtest_summary.md`, which was fixed before this comparison.

## MASE by series

| Series | AutoARIMA_log / BottomUp | SeasonalNaive / base | TimesFM-2.5 / BottomUp | TimesFM-2.5 / base |
|---|---:|---:|---:|---:|
| Google Cloud | 0.57 | 2.45 | 0.92 | 0.92 |
| Google Network | 0.18 | 0.21 | 0.41 | 0.41 |
| Google Services | 0.29 | 1.17 | 0.54 | 0.67 |
| Other Bets | 1.31 | 1.32 | 1.28 | 1.28 |
| Search & other | 0.42 | 1.27 | 0.67 | 0.67 |
| Subscriptions, platforms & devices | 0.46 | 1.49 | 0.73 | 0.73 |
| Total revenue excl. hedging | 0.33 | 1.44 | 0.61 | 0.76 |
| YouTube ads | 0.35 | 0.96 | 0.50 | 0.50 |

Runtime: 30s on CPU.
