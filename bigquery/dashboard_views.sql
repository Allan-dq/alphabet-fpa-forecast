-- BigQuery-only views shaped for the Looker Studio dashboard. PROJECT.DATASET is substituted by load_bigquery.sh.
CREATE OR REPLACE VIEW `PROJECT.DATASET.dash_revenue_lines` AS
SELECT period_end, fiscal_quarter, line_name AS revenue_line, revenue, yoy_growth
FROM `PROJECT.DATASET.revenue_mix`
WHERE line <> 'hedging_gains_losses';

CREATE OR REPLACE VIEW `PROJECT.DATASET.dash_pnl` AS
SELECT period_end, fiscal_quarter, total_revenue, operating_income, operating_margin, capex
FROM `PROJECT.DATASET.pnl_quarterly`;

-- One-quarter-ahead forecasts of total revenue excl. hedging vs actuals (selected configuration).
CREATE OR REPLACE VIEW `PROJECT.DATASET.dash_forecast_track` AS
SELECT
  f.fiscal_quarter,
  q.period_end,
  f.forecast,
  f.actual,
  f.error AS variance,
  SAFE_DIVIDE(f.error, f.forecast) AS variance_pct
FROM `PROJECT.DATASET.forecast_vs_actual` f
JOIN `PROJECT.DATASET.fact_quarterly` q ON q.fiscal_quarter = f.fiscal_quarter AND q.line = f.line
WHERE f.model = 'MODEL_LABEL' AND f.horizon = 1 AND f.line = 'total_revenue_ex_hedging'
  AND f.run_type IN ('backtest', 'holdout');

-- Actual history plus the live 8-quarter forecast with intervals, for one time-series chart.
CREATE OR REPLACE VIEW `PROJECT.DATASET.dash_forecast` AS
SELECT period_end, 'Actual' AS series, value_m AS revenue, CAST(NULL AS FLOAT64) AS lo_80, CAST(NULL AS FLOAT64) AS hi_80
FROM `PROJECT.DATASET.fact_quarterly`
WHERE line = 'total_revenue_ex_hedging' AND fiscal_quarter >= '2019Q1'
UNION ALL
SELECT LAST_DAY(PARSE_DATE('%Y-%m-%d', CONCAT(SUBSTR(fiscal_quarter, 1, 4), '-',
         LPAD(CAST(CAST(SUBSTR(fiscal_quarter, 6, 1) AS INT64) * 3 AS STRING), 2, '0'), '-01')), MONTH),
       'Forecast', forecast, lo_80, hi_80
FROM `PROJECT.DATASET.forecasts`
WHERE run_type = 'live' AND model = 'MODEL_LABEL' AND line = 'total_revenue_ex_hedging';
