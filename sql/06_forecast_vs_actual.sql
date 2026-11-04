-- Forecasts written by the forecasting step, joined to actuals where they exist.
-- `forecasts` holds every backtest window (cutoff < fiscal_quarter) and the live forecast.
CREATE OR REPLACE VIEW forecast_vs_actual AS
SELECT
  fc.run_type,
  fc.model,
  fc.cutoff,
  fc.fiscal_quarter,
  fc.horizon,
  fc.line,
  fc.forecast,
  fc.lo_80, fc.hi_80, fc.lo_95, fc.hi_95,
  act.value_m                                              AS actual,
  act.value_m - fc.forecast                                AS error,
  ABS(act.value_m - fc.forecast) / NULLIF(ABS(act.value_m), 0) AS abs_pct_error,
  CASE WHEN act.value_m IS NULL OR fc.lo_80 IS NULL THEN NULL
       WHEN act.value_m BETWEEN fc.lo_80 AND fc.hi_80 THEN 1 ELSE 0 END AS in_80,
  CASE WHEN act.value_m IS NULL OR fc.lo_95 IS NULL THEN NULL
       WHEN act.value_m BETWEEN fc.lo_95 AND fc.hi_95 THEN 1 ELSE 0 END AS in_95
FROM forecasts fc
LEFT JOIN fact_quarterly act
  ON act.line = fc.line AND act.fiscal_quarter = fc.fiscal_quarter;
