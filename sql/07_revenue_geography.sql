-- Revenue by region (US, EMEA, APAC, Other Americas): share, YoY and QoQ growth.
-- 2017-2018 regional figures include hedging gains/losses; from 2019 they exclude them (restated).
CREATE OR REPLACE VIEW revenue_geography AS
WITH geo AS (
  SELECT f.fiscal_quarter, f.period_end, f.line, d.line_name AS region, d.sort_order, f.value_m AS revenue
  FROM fact_quarterly f
  JOIN dim_line d ON d.line = f.line
  WHERE d.category = 'geography'
),
tot AS (
  SELECT fiscal_quarter, SUM(revenue) AS regions_total
  FROM geo
  GROUP BY fiscal_quarter
)
SELECT
  geo.fiscal_quarter,
  geo.period_end,
  geo.line,
  geo.region,
  geo.sort_order,
  geo.revenue,
  geo.revenue / NULLIF(tot.regions_total, 0)                                                              AS share,
  geo.revenue / NULLIF(LAG(geo.revenue, 4) OVER (PARTITION BY geo.line ORDER BY geo.period_end), 0) - 1 AS yoy_growth,
  geo.revenue / NULLIF(LAG(geo.revenue, 1) OVER (PARTITION BY geo.line ORDER BY geo.period_end), 0) - 1 AS qoq_growth,
  geo.fiscal_quarter < '2019Q1'                                                                            AS includes_hedging
FROM geo
JOIN tot ON tot.fiscal_quarter = geo.fiscal_quarter;
