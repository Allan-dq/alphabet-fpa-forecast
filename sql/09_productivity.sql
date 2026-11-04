-- Headcount and productivity. Headcount is a count of employees at quarter end (earnings releases);
-- money columns are USD millions, per-employee columns are USD thousands.
CREATE OR REPLACE VIEW productivity AS
SELECT
  t.fiscal_quarter,
  t.period_end,
  h.value_m                                                                         AS employees,
  h.value_m / NULLIF(LAG(h.value_m, 4) OVER (ORDER BY t.period_end), 0) - 1        AS employees_yoy,
  t.revenue_ttm * 1000 / NULLIF(h.value_m, 0)                                      AS revenue_ttm_per_employee_k,
  t.operating_income_ttm * 1000 / NULLIF(h.value_m, 0)                             AS operating_income_ttm_per_employee_k,
  (p.research_development + p.sales_marketing + p.general_administrative) * 1000
    / NULLIF(h.value_m, 0)                                                         AS opex_per_employee_k_quarter
FROM ttm_metrics t
JOIN fact_quarterly h ON h.fiscal_quarter = t.fiscal_quarter AND h.line = 'headcount'
JOIN pnl_quarterly p ON p.fiscal_quarter = t.fiscal_quarter;
