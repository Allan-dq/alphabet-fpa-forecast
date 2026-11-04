# Backtest results

Rolling-origin backtest, expanding window, one-quarter steps. 12 forecast origins (2023Q2 to 2026Q1),
horizons 1-4 quarters, targets up to 2026Q2. The latest quarter
(2026Q3) is held out of the backtest and used only for the variance analysis. 42 scored
forecasts per series. Training data start in 2019Q1.

**Selection rule (fixed before running, see `docs/experiments.md`):** lowest mean MASE across the 8 hierarchy series (coherent forecasts; the incumbent AutoARIMA + BottomUp is kept unless beaten by >= 3%), then the interval kind with the lower mean scaled interval score.
**Selected:** `AutoARIMA_log` base forecasts reconciled with `BottomUp`, `model` prediction intervals.

## Headline

| | Selected (AutoARIMA_log + BottomUp, model intervals) | Seasonal naive | Random walk with drift |
|---|---:|---:|---:|
| Total revenue excl. hedging: WAPE | 3.2% | 14.0% | 5.3% |
| Total revenue excl. hedging: MASE | 0.33 | 1.44 | 0.55 |
| Mean MASE, 8 series | 0.49 | 1.29 | 0.76 |
| 80% interval coverage (all series) | 93.2% | 70.2% | 78.9% |
| 95% interval coverage (all series) | 96.1% | 92.9% | 88.4% |

## Selected model by series

| Series | MAPE | WAPE | MASE | Seasonal-naive WAPE | Seasonal-naive MASE | 80% coverage | 95% coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| Total revenue excl. hedging | 3.2% | 3.2% | 0.33 | 14.0% | 1.44 | 100.0% | 100.0% |
| Google Services | 2.8% | 2.8% | 0.29 | 11.3% | 1.17 | 100.0% | 100.0% |
| Google Cloud | 5.6% | 7.3% | 0.57 | 30.0% | 2.45 | 61.9% | 73.8% |
| Other Bets | 23.4% | 24.2% | 1.31 | 23.4% | 1.32 | 90.5% | 95.2% |
| Search & other | 4.2% | 4.1% | 0.42 | 12.4% | 1.27 | 100.0% | 100.0% |
| YouTube ads | 4.1% | 4.1% | 0.35 | 11.3% | 0.96 | 100.0% | 100.0% |
| Google Network | 2.1% | 2.1% | 0.18 | 2.5% | 0.21 | 100.0% | 100.0% |
| Subscriptions, platforms & devices | 4.7% | 4.8% | 0.46 | 15.2% | 1.49 | 92.9% | 100.0% |

## All model x reconciliation combinations (sorted by mean MASE)

`base` = unreconciled base forecasts, shown for reference; only coherent combinations were eligible for selection.
`intervals`: `model` = the model's own prediction intervals, `conformal` = split-conformal intervals (point forecasts are identical).
`mean_msis` = mean scaled interval score over the 80% and 95% levels (lower is better).

| rank | model | method | intervals | mean_mase | mean_wape | total_wape | total_mase | mean_msis | coverage_80 | coverage_95 |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | AutoARIMA_log | BottomUp | model | 0.490 | 6.6% | 3.2% | 0.333 | 4.44 | 93.2% | 96.1% |
| 2 | AutoARIMA_log | BottomUp | conformal | 0.490 | 6.6% | 3.2% | 0.333 | 4.98 | 78.9% | 89.3% |
| 3 | AutoARIMA_log | MinT | model | 0.496 | 6.7% | 2.9% | 0.303 | 4.41 | 92.6% | 95.8% |
| 4 | AutoARIMA_log | MinT | conformal | 0.496 | 6.7% | 2.9% | 0.303 | 5.21 | 82.1% | 89.0% |
| 5 | AutoARIMA | BottomUp | model | 0.514 | 6.7% | 3.9% | 0.403 | 4.79 | 76.8% | 86.6% |
| 6 | AutoARIMA | BottomUp | conformal | 0.514 | 6.7% | 3.9% | 0.403 | 5.97 | 61.9% | 72.3% |
| 7 | AutoARIMA_log | base | model | 0.518 | 6.8% | 4.4% | 0.453 | 4.39 | 93.8% | 96.1% |
| 8 | AutoARIMA_log | base | conformal | 0.518 | 6.8% | 4.4% | 0.453 | 5.32 | 83.3% | 86.6% |
| 9 | AutoARIMA | MinT | model | 0.520 | 6.8% | 3.9% | 0.401 | 4.73 | 79.5% | 87.2% |
| 10 | AutoARIMA | MinT | conformal | 0.520 | 6.8% | 3.9% | 0.401 | 5.91 | 65.8% | 74.7% |
| 11 | AutoARIMA | base | model | 0.525 | 6.8% | 4.4% | 0.449 | 4.80 | 79.5% | 87.8% |
| 12 | AutoARIMA | base | conformal | 0.525 | 6.8% | 4.4% | 0.449 | 6.12 | 68.8% | 72.9% |
| 13 | AutoARIMA_d1 | MinT | model | 0.541 | 7.1% | 4.1% | 0.420 | 5.27 | 78.9% | 86.0% |
| 14 | AutoARIMA_d1 | MinT | conformal | 0.541 | 7.1% | 4.1% | 0.420 | 6.42 | 66.1% | 75.0% |
| 15 | AutoARIMA_d1 | BottomUp | model | 0.542 | 7.0% | 4.3% | 0.437 | 5.37 | 75.3% | 84.2% |
| 16 | AutoARIMA_d1 | BottomUp | conformal | 0.542 | 7.0% | 4.3% | 0.437 | 6.52 | 62.5% | 72.0% |
| 17 | AutoARIMA | TopDown | conformal | 0.547 | 7.0% | 4.4% | 0.449 | 5.24 | 58.9% | 79.5% |
| 18 | AutoARIMA | TopDown | model | 0.547 | 7.0% | 4.4% | 0.449 | 5.24 | 58.9% | 79.5% |
| 19 | AutoARIMA_d1 | base | model | 0.548 | 7.1% | 4.4% | 0.449 | 5.33 | 78.6% | 86.3% |
| 20 | AutoARIMA_d1 | base | conformal | 0.548 | 7.1% | 4.4% | 0.449 | 6.60 | 69.0% | 73.2% |
| 21 | AutoARIMA_d1 | TopDown | conformal | 0.556 | 7.2% | 4.4% | 0.449 | 5.67 | 61.6% | 78.6% |
| 22 | AutoARIMA_d1 | TopDown | model | 0.556 | 7.2% | 4.4% | 0.449 | 5.67 | 61.6% | 78.6% |
| 23 | Combo | BottomUp | model | 0.567 | 7.1% | 5.1% | 0.522 | 5.18 | 77.4% | 86.6% |
| 24 | Combo | BottomUp | conformal | 0.567 | 7.1% | 5.1% | 0.522 | 6.09 | 59.5% | 71.1% |
| 25 | Combo | base | model | 0.571 | 7.1% | 5.5% | 0.571 | 5.16 | 80.7% | 89.0% |
| 26 | Combo | base | conformal | 0.571 | 7.1% | 5.5% | 0.571 | 6.12 | 67.6% | 71.4% |
| 27 | Combo | TopDown | conformal | 0.590 | 7.3% | 5.5% | 0.571 | 8.99 | 68.5% | 81.2% |
| 28 | Combo | TopDown | model | 0.590 | 7.3% | 5.5% | 0.571 | 8.99 | 68.5% | 81.2% |
| 29 | AutoARIMA_log | TopDown | conformal | 0.608 | 7.9% | 4.4% | 0.453 | 5.19 | 58.0% | 76.5% |
| 30 | AutoARIMA_log | TopDown | model | 0.608 | 7.9% | 4.4% | 0.453 | 5.19 | 58.0% | 76.5% |
| 31 | Combo | MinT | model | 0.616 | 7.6% | 5.5% | 0.570 | 4.48 | 88.4% | 96.4% |
| 32 | Combo | MinT | conformal | 0.616 | 7.6% | 5.5% | 0.570 | 5.09 | 71.4% | 83.3% |
| 33 | AutoTheta | base | model | 0.662 | 8.4% | 4.8% | 0.496 | 6.33 | 76.2% | 82.1% |
| 34 | AutoTheta | base | conformal | 0.662 | 8.4% | 4.8% | 0.496 | 7.55 | 57.4% | 62.5% |
| 35 | AutoTheta | TopDown | conformal | 0.664 | 8.4% | 4.8% | 0.496 | 9.72 | 74.1% | 87.8% |
| 36 | AutoTheta | TopDown | model | 0.664 | 8.4% | 4.8% | 0.496 | 9.72 | 74.1% | 87.8% |
| 37 | AutoTheta | BottomUp | model | 0.668 | 8.4% | 4.9% | 0.505 | 6.33 | 71.4% | 80.7% |
| 38 | AutoTheta | BottomUp | conformal | 0.668 | 8.4% | 4.9% | 0.505 | 7.43 | 50.3% | 63.7% |
| 39 | AutoTheta | MinT | model | 0.678 | 8.6% | 4.8% | 0.496 | 5.40 | 82.1% | 92.6% |
| 40 | AutoTheta | MinT | conformal | 0.678 | 8.6% | 4.8% | 0.496 | 7.16 | 61.0% | 74.7% |
| 41 | AutoETS | BottomUp | model | 0.712 | 8.5% | 7.3% | 0.751 | 5.48 | 72.3% | 85.7% |
| 42 | AutoETS | BottomUp | conformal | 0.712 | 8.5% | 7.3% | 0.751 | 7.36 | 42.6% | 61.6% |
| 43 | AutoETS | MinT | model | 0.723 | 8.6% | 7.5% | 0.771 | 5.41 | 75.0% | 87.5% |
| 44 | AutoETS | MinT | conformal | 0.723 | 8.6% | 7.5% | 0.771 | 6.93 | 44.6% | 64.0% |
| 45 | AutoETS | base | model | 0.726 | 8.7% | 8.6% | 0.885 | 5.33 | 78.3% | 88.7% |
| 46 | AutoETS | base | conformal | 0.726 | 8.7% | 8.6% | 0.885 | 7.35 | 51.2% | 57.4% |
| 47 | RWD | BottomUp | model | 0.757 | 9.6% | 5.3% | 0.549 | 6.67 | 72.9% | 83.9% |
| 48 | RWD | BottomUp | conformal | 0.757 | 9.6% | 5.3% | 0.549 | 7.71 | 44.9% | 61.3% |
| 49 | RWD | MinT | model | 0.757 | 9.6% | 5.3% | 0.549 | 6.70 | 77.7% | 88.1% |
| 50 | RWD | MinT | conformal | 0.757 | 9.6% | 5.3% | 0.549 | 7.33 | 46.7% | 68.2% |
| 51 | RWD | TopDown | conformal | 0.757 | 9.6% | 5.3% | 0.549 | 6.96 | 69.3% | 80.7% |
| 52 | RWD | TopDown | model | 0.757 | 9.6% | 5.3% | 0.549 | 6.96 | 69.3% | 80.7% |
| 53 | RWD | base | model | 0.757 | 9.6% | 5.3% | 0.549 | 6.71 | 78.9% | 88.4% |
| 54 | RWD | base | conformal | 0.757 | 9.6% | 5.3% | 0.549 | 7.63 | 56.0% | 61.3% |
| 55 | AutoETS | TopDown | conformal | 0.803 | 9.4% | 8.6% | 0.885 | 8.19 | 50.6% | 64.0% |
| 56 | AutoETS | TopDown | model | 0.803 | 9.4% | 8.6% | 0.885 | 8.19 | 50.6% | 64.0% |
| 57 | SeasonalNaive | BottomUp | model | 1.291 | 15.0% | 14.0% | 1.440 | 7.90 | 58.0% | 89.0% |
| 58 | SeasonalNaive | BottomUp | conformal | 1.291 | 15.0% | 14.0% | 1.440 | 11.36 | 25.6% | 44.6% |
| 59 | SeasonalNaive | MinT | model | 1.291 | 15.0% | 14.0% | 1.440 | 7.76 | 65.8% | 89.9% |
| 60 | SeasonalNaive | MinT | conformal | 1.291 | 15.0% | 14.0% | 1.440 | 10.29 | 27.4% | 47.0% |
| 61 | SeasonalNaive | TopDown | conformal | 1.291 | 15.0% | 14.0% | 1.440 | 7.51 | 74.7% | 83.9% |
| 62 | SeasonalNaive | TopDown | model | 1.291 | 15.0% | 14.0% | 1.440 | 7.51 | 74.7% | 83.9% |
| 63 | SeasonalNaive | base | model | 1.291 | 15.0% | 14.0% | 1.440 | 7.50 | 70.2% | 92.9% |
| 64 | SeasonalNaive | base | conformal | 1.291 | 15.0% | 14.0% | 1.440 | 11.37 | 28.0% | 41.4% |

Files: `backtest_overall.csv`, `backtest_per_line.csv`, `backtest_by_horizon.csv`.
