-- Backtest accuracy computed in SQL from the forecast_vs_actual view.
-- Must agree with the Python metrics in reports/backtest_per_line.csv (tested).
SELECT
  model,
  line,
  COUNT(*)                                        AS n,
  AVG(abs_pct_error)                              AS mape,
  SUM(ABS(error)) / NULLIF(SUM(ABS(actual)), 0)   AS wape,
  AVG(in_80)                                      AS coverage_80,
  AVG(in_95)                                      AS coverage_95
FROM forecast_vs_actual
WHERE run_type = 'backtest'
GROUP BY model, line
ORDER BY model, line
