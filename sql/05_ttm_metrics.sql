-- Trailing-twelve-month (last 4 quarters) metrics; NULL until 4 quarters are available.
CREATE OR REPLACE VIEW ttm_metrics AS
WITH w AS (
  SELECT
    fiscal_quarter,
    period_end,
    COUNT(total_revenue)     OVER w4 AS n_q,
    SUM(total_revenue)       OVER w4 AS revenue_ttm,
    SUM(operating_income)    OVER w4 AS operating_income_ttm,
    SUM(capex)               OVER w4 AS capex_ttm,
    COUNT(google_cloud)      OVER w4 AS n_cloud,
    SUM(google_cloud)        OVER w4 AS cloud_revenue_ttm,
    SUM(search_other)        OVER w4 AS search_revenue_ttm,
    SUM(youtube_ads)         OVER w4 AS youtube_revenue_ttm
  FROM pnl_quarterly
  WINDOW w4 AS (ORDER BY period_end ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)
)
SELECT
  fiscal_quarter,
  period_end,
  CASE WHEN n_q = 4 THEN revenue_ttm END                                   AS revenue_ttm,
  CASE WHEN n_q = 4 THEN operating_income_ttm END                          AS operating_income_ttm,
  CASE WHEN n_q = 4 THEN operating_income_ttm / NULLIF(revenue_ttm, 0) END AS operating_margin_ttm,
  CASE WHEN n_q = 4 THEN capex_ttm END                                     AS capex_ttm,
  CASE WHEN n_q = 4 THEN capex_ttm / NULLIF(revenue_ttm, 0) END            AS capex_intensity_ttm,
  CASE WHEN n_cloud = 4 THEN cloud_revenue_ttm END                         AS cloud_revenue_ttm,
  CASE WHEN n_cloud = 4 THEN search_revenue_ttm END                        AS search_revenue_ttm,
  CASE WHEN n_cloud = 4 THEN youtube_revenue_ttm END                       AS youtube_revenue_ttm,
  CASE WHEN n_q = 4 THEN
    revenue_ttm / NULLIF(LAG(revenue_ttm, 4) OVER (ORDER BY period_end), 0) - 1
  END                                                                      AS revenue_ttm_yoy
FROM w;
