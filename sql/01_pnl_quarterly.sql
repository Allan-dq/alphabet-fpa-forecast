-- One row per fiscal quarter: revenue build, cost lines, operating income and margin (USD millions).
CREATE OR REPLACE VIEW pnl_quarterly AS
SELECT
  fiscal_quarter,
  MAX(period_end)                                                              AS period_end,
  MAX(CASE WHEN line = 'search_other'                    THEN value_m END)     AS search_other,
  MAX(CASE WHEN line = 'youtube_ads'                     THEN value_m END)     AS youtube_ads,
  MAX(CASE WHEN line = 'google_network'                  THEN value_m END)     AS google_network,
  MAX(CASE WHEN line = 'subscriptions_platforms_devices' THEN value_m END)     AS subscriptions_platforms_devices,
  MAX(CASE WHEN line = 'google_services_revenue'         THEN value_m END)     AS google_services_revenue,
  MAX(CASE WHEN line = 'google_cloud'                    THEN value_m END)     AS google_cloud,
  MAX(CASE WHEN line = 'other_bets_revenue'              THEN value_m END)     AS other_bets_revenue,
  MAX(CASE WHEN line = 'hedging_gains_losses'            THEN value_m END)     AS hedging_gains_losses,
  MAX(CASE WHEN line = 'total_revenue'                   THEN value_m END)     AS total_revenue,
  MAX(CASE WHEN line = 'cost_of_revenues'                THEN value_m END)     AS cost_of_revenues,
  MAX(CASE WHEN line = 'research_development'            THEN value_m END)     AS research_development,
  MAX(CASE WHEN line = 'sales_marketing'                 THEN value_m END)     AS sales_marketing,
  MAX(CASE WHEN line = 'general_administrative'          THEN value_m END)     AS general_administrative,
  COALESCE(MAX(CASE WHEN line = 'ec_fines'               THEN value_m END), 0) AS ec_fines,
  MAX(CASE WHEN line = 'total_costs_expenses'            THEN value_m END)     AS total_costs_expenses,
  MAX(CASE WHEN line = 'total_revenue' THEN value_m END)
    - MAX(CASE WHEN line = 'cost_of_revenues' THEN value_m END)               AS gross_profit,
  MAX(CASE WHEN line = 'operating_income'                THEN value_m END)     AS operating_income,
  MAX(CASE WHEN line = 'operating_income' THEN value_m END)
    / NULLIF(MAX(CASE WHEN line = 'total_revenue' THEN value_m END), 0)       AS operating_margin,
  MAX(CASE WHEN line = 'capex'                           THEN value_m END)     AS capex,
  MAX(CASE WHEN restated THEN 1 ELSE 0 END) = 1                               AS any_line_restated
FROM fact_quarterly
GROUP BY fiscal_quarter;
