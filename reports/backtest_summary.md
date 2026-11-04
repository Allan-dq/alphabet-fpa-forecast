# Backtest results

Rolling-origin backtest, expanding window, one-quarter steps. 12 forecast origins (2023Q2 to 2026Q1),
horizons 1-4 quarters, targets up to 2026Q2. The latest quarter
(2026Q3) is held out of the backtest and used only for the variance analysis. 42 scored
forecasts per series. Training data start in 2019Q1.

**Selection rule (fixed before running):** lowest mean MASE across the 8 hierarchy series, all backtest windows, horizons 1-4, coherent forecasts only.
**Selected:** `AutoARIMA` base forecasts reconciled with `BottomUp`.

## Headline

| | Selected (AutoARIMA + BottomUp) | Seasonal naive | Random walk with drift |
|---|---:|---:|---:|
| Total revenue excl. hedging: WAPE | 3.9% | 14.0% | 5.3% |
| Total revenue excl. hedging: MASE | 0.40 | 1.44 | 0.55 |
| Mean MASE, 8 series | 0.51 | 1.29 | 0.76 |
| 80% interval coverage (all series) | 76.8% | 70.2% | 78.9% |
| 95% interval coverage (all series) | 86.6% | 92.9% | 88.4% |

## Selected model by series

| Series | MAPE | WAPE | MASE | Seasonal-naive WAPE | Seasonal-naive MASE | 80% coverage | 95% coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| Total revenue excl. hedging | 3.7% | 3.9% | 0.40 | 14.0% | 1.44 | 71.4% | 85.7% |
| Google Services | 2.8% | 2.9% | 0.30 | 11.3% | 1.17 | 85.7% | 100.0% |
| Google Cloud | 8.4% | 10.1% | 0.82 | 30.0% | 2.45 | 19.0% | 35.7% |
| Other Bets | 20.7% | 22.1% | 1.24 | 23.4% | 1.32 | 83.3% | 95.2% |
| Search & other | 3.8% | 3.9% | 0.40 | 12.4% | 1.27 | 97.6% | 100.0% |
| YouTube ads | 1.6% | 1.6% | 0.14 | 11.3% | 0.96 | 100.0% | 100.0% |
| Google Network | 3.6% | 3.6% | 0.28 | 2.5% | 0.21 | 90.5% | 92.9% |
| Subscriptions, platforms & devices | 5.3% | 5.5% | 0.54 | 15.2% | 1.49 | 66.7% | 83.3% |

## All model x reconciliation combinations (sorted by mean MASE)

`base` = unreconciled base forecasts, shown for reference; only coherent combinations were eligible for selection.

| rank | model | method | mean_mase | mean_wape | total_wape | total_mase | coverage_80 | coverage_95 |
|---:|---|---|---:|---:|---:|---:|---:|---:|
| 1 | AutoARIMA | BottomUp | 0.514 | 6.7% | 3.9% | 0.403 | 76.8% | 86.6% |
| 2 | AutoARIMA | MinT | 0.520 | 6.8% | 3.9% | 0.401 | 79.5% | 87.2% |
| 3 | AutoARIMA | base | 0.525 | 6.8% | 4.4% | 0.449 | 79.5% | 87.8% |
| 4 | AutoARIMA | TopDown | 0.547 | 7.0% | 4.4% | 0.449 | 58.9% | 79.5% |
| 5 | AutoTheta | base | 0.662 | 8.4% | 4.8% | 0.496 | 76.2% | 82.1% |
| 6 | AutoTheta | TopDown | 0.664 | 8.4% | 4.8% | 0.496 | 74.1% | 87.8% |
| 7 | AutoTheta | BottomUp | 0.668 | 8.4% | 4.9% | 0.505 | 71.4% | 80.7% |
| 8 | AutoTheta | MinT | 0.678 | 8.6% | 4.8% | 0.496 | 82.1% | 92.6% |
| 9 | AutoETS | BottomUp | 0.712 | 8.5% | 7.3% | 0.751 | 72.3% | 85.7% |
| 10 | AutoETS | MinT | 0.723 | 8.6% | 7.5% | 0.771 | 75.0% | 87.5% |
| 11 | AutoETS | base | 0.726 | 8.7% | 8.6% | 0.885 | 78.3% | 88.7% |
| 12 | RWD | BottomUp | 0.757 | 9.6% | 5.3% | 0.549 | 72.9% | 83.9% |
| 13 | RWD | MinT | 0.757 | 9.6% | 5.3% | 0.549 | 77.7% | 88.1% |
| 14 | RWD | TopDown | 0.757 | 9.6% | 5.3% | 0.549 | 69.3% | 80.7% |
| 15 | RWD | base | 0.757 | 9.6% | 5.3% | 0.549 | 78.9% | 88.4% |
| 16 | AutoETS | TopDown | 0.803 | 9.4% | 8.6% | 0.885 | 50.6% | 64.0% |
| 17 | SeasonalNaive | BottomUp | 1.291 | 15.0% | 14.0% | 1.440 | 58.0% | 89.0% |
| 18 | SeasonalNaive | MinT | 1.291 | 15.0% | 14.0% | 1.440 | 65.8% | 89.9% |
| 19 | SeasonalNaive | TopDown | 1.291 | 15.0% | 14.0% | 1.440 | 74.7% | 83.9% |
| 20 | SeasonalNaive | base | 1.291 | 15.0% | 14.0% | 1.440 | 70.2% | 92.9% |

Files: `backtest_overall.csv`, `backtest_per_line.csv`, `backtest_by_horizon.csv`.
