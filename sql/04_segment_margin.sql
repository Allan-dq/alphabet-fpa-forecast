-- Segment revenue, operating income and margin (segment reporting starts 2020Q1).
CREATE OR REPLACE VIEW segment_margin AS
WITH seg AS (
  SELECT 'Google Services' AS segment, 'google_services_revenue' AS rev_line, 'oi_google_services' AS oi_line, 1 AS sort_order
  UNION ALL SELECT 'Google Cloud', 'google_cloud', 'oi_google_cloud', 2
  UNION ALL SELECT 'Other Bets', 'other_bets_revenue', 'oi_other_bets', 3
  UNION ALL SELECT 'Alphabet-level activities', NULL, 'oi_alphabet_level', 4
)
SELECT
  oi.fiscal_quarter,
  oi.period_end,
  seg.segment,
  seg.sort_order,
  rv.value_m                               AS revenue,
  oi.value_m                               AS operating_income,
  oi.value_m / NULLIF(rv.value_m, 0)       AS operating_margin,
  oi.restated                              AS operating_income_restated
FROM seg
JOIN fact_quarterly oi ON oi.line = seg.oi_line
LEFT JOIN fact_quarterly rv ON rv.line = seg.rev_line AND rv.fiscal_quarter = oi.fiscal_quarter;
