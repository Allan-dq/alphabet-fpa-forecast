-- Cost lines as a share of revenue.
CREATE OR REPLACE VIEW opex_ratios AS
SELECT
  fiscal_quarter,
  period_end,
  total_revenue,
  cost_of_revenues        / NULLIF(total_revenue, 0)                                   AS cost_of_revenues_pct,
  research_development    / NULLIF(total_revenue, 0)                                   AS research_development_pct,
  sales_marketing         / NULLIF(total_revenue, 0)                                   AS sales_marketing_pct,
  general_administrative  / NULLIF(total_revenue, 0)                                   AS general_administrative_pct,
  (research_development + sales_marketing + general_administrative)
                          / NULLIF(total_revenue, 0)                                   AS opex_pct,
  gross_profit            / NULLIF(total_revenue, 0)                                   AS gross_margin,
  operating_margin,
  capex                   / NULLIF(total_revenue, 0)                                   AS capex_pct
FROM pnl_quarterly;
