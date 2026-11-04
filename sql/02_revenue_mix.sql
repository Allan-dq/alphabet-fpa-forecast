-- Revenue by line: share of total, year-over-year and quarter-over-quarter growth.
CREATE OR REPLACE VIEW revenue_mix AS
WITH rev AS (
  SELECT f.fiscal_quarter, f.period_end, f.line, d.line_name, d.sort_order, f.value_m AS revenue
  FROM fact_quarterly f
  JOIN dim_line d ON d.line = f.line
  WHERE d.category = 'revenue'
),
tot AS (
  SELECT fiscal_quarter, value_m AS total_revenue
  FROM fact_quarterly
  WHERE line = 'total_revenue'
)
SELECT
  rev.fiscal_quarter,
  rev.period_end,
  rev.line,
  rev.line_name,
  rev.sort_order,
  rev.revenue,
  rev.revenue / NULLIF(tot.total_revenue, 0)                                          AS share_of_total,
  rev.revenue / NULLIF(LAG(rev.revenue, 4) OVER (PARTITION BY rev.line ORDER BY rev.period_end), 0) - 1 AS yoy_growth,
  rev.revenue / NULLIF(LAG(rev.revenue, 1) OVER (PARTITION BY rev.line ORDER BY rev.period_end), 0) - 1 AS qoq_growth
FROM rev
JOIN tot ON tot.fiscal_quarter = rev.fiscal_quarter;
