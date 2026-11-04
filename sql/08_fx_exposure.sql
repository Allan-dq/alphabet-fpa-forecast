-- FX lens: non-US revenue, its share, and hedging gains/losses relative to it.
CREATE OR REPLACE VIEW fx_exposure AS
SELECT
  p.fiscal_quarter,
  p.period_end,
  SUM(CASE WHEN g.line <> 'revenue_us' THEN g.revenue END)                                   AS non_us_revenue,
  SUM(CASE WHEN g.line <> 'revenue_us' THEN g.revenue END) / NULLIF(SUM(g.revenue), 0)      AS non_us_share,
  MAX(p.hedging_gains_losses)                                                                AS hedging_gains_losses,
  MAX(p.hedging_gains_losses) / NULLIF(SUM(CASE WHEN g.line <> 'revenue_us' THEN g.revenue END), 0)
                                                                                             AS hedging_pct_of_non_us
FROM pnl_quarterly p
JOIN revenue_geography g ON g.fiscal_quarter = p.fiscal_quarter
WHERE p.fiscal_quarter >= '2019Q1'
GROUP BY p.fiscal_quarter, p.period_end;
