# Challengers: TimesFM 2.5 and 3.0 (zero-shot)

Same 12 origins (2023Q2 to 2026Q1), horizons 1-4, targets up to 2026Q2, same metrics.
Both models are used zero-shot on each series' own history:
- `google/timesfm-2.5-200m-pytorch` (Apache-2.0);
- `google/timesfm-3.0-pytorch` (TimesFM Non-Commercial License v1.0, used here for a non-commercial educational project; weights are not redistributed).

Both models output the 10th–90th percentiles, so only 80% coverage is reported. For BottomUp, interval sums are not valid, so no coverage is shown.

| model | method | mean_mase | mean_wape | coverage_80 | total_wape | total_mase |
|---|---|---:|---:|---|---:|---:|
| AutoARIMA_log | BottomUp | 0.490 | 6.6% | 93.2% | 3.2% | 0.333 |
| TimesFM-3.0 | BottomUp | 0.560 | 7.1% |  | 4.0% | 0.409 |
| TimesFM-3.0 | base | 0.563 | 7.2% | 67.0% | 4.2% | 0.424 |
| TimesFM-2.5 | BottomUp | 0.709 | 8.7% |  | 5.9% | 0.607 |
| TimesFM-2.5 | base | 0.744 | 9.0% | 60.7% | 7.3% | 0.761 |
| SeasonalNaive | base | 1.291 | 15.0% | 70.2% | 14.0% | 1.440 |

Lowest mean MASE: **AutoARIMA_log / BottomUp** (0.490).
The production model was **not** changed: it was selected by the rule in `backtest_summary.md`, which was fixed before this comparison.

## MASE by series

| Series | AutoARIMA_log / BottomUp | SeasonalNaive / base | TimesFM-2.5 / BottomUp | TimesFM-2.5 / base | TimesFM-3.0 / BottomUp | TimesFM-3.0 / base |
|---|---:|---:|---:|---:|---:|---:|
| Google Cloud | 0.57 | 2.45 | 0.92 | 0.92 | 1.09 | 1.09 |
| Google Network | 0.18 | 0.21 | 0.41 | 0.41 | 0.38 | 0.38 |
| Google Services | 0.29 | 1.17 | 0.54 | 0.67 | 0.28 | 0.28 |
| Other Bets | 1.31 | 1.32 | 1.28 | 1.28 | 1.18 | 1.18 |
| Search & other | 0.42 | 1.27 | 0.67 | 0.67 | 0.32 | 0.32 |
| Subscriptions, platforms & devices | 0.46 | 1.49 | 0.73 | 0.73 | 0.55 | 0.55 |
| Total revenue excl. hedging | 0.33 | 1.44 | 0.61 | 0.76 | 0.41 | 0.42 |
| YouTube ads | 0.35 | 0.96 | 0.50 | 0.50 | 0.27 | 0.27 |

Runtime: 55s on CPU.
