# Next-4-quarter P&L forecast (2026Q4 to 2027Q3)

USD millions. Revenue lines: `AutoARIMA_log` + `BottomUp` forecast with data through 2026Q3.
Hedging gains (losses) planned at $0M. Costs: `assumptions.yaml`.

|  | 2026Q4 | 2027Q1 | 2027Q2 | 2027Q3 | Next 4Q | Prior 4Q (actual) | YoY % |
|---|---:|---:|---:|---:|---:|---:|---:|
| Search & other | 72,301.9 | 69,530.4 | 72,888.5 | 77,142.0 | 291,862.7 | 250,093.0 | +16.7% |
| YouTube ads | 12,562.9 | 10,644.3 | 11,634.7 | 11,840.2 | 46,682.1 | 43,528.0 | +7.2% |
| Google Network | 8,372.3 | 7,465.6 | 7,635.5 | 7,830.2 | 31,303.6 | 29,557.0 | +5.9% |
| Subscriptions, platforms & devices | 16,256.3 | 14,406.9 | 15,273.1 | 16,946.0 | 62,882.3 | 53,163.0 | +18.3% |
| Google Cloud | 36,182.1 | 41,405.7 | 46,600.3 | 51,949.1 | 176,137.2 | 93,169.0 | +89.1% |
| Other Bets | 425.0 | 438.7 | 452.7 | 467.2 | 1,783.6 | 1,535.0 | +16.2% |
| Hedging gains (losses) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 53.0 | -100.0% |
| Total revenues | 146,100.5 | 143,891.6 | 154,484.7 | 166,174.7 | 610,651.6 | 471,098.0 | +29.6% |
| Cost of revenues | 56,227.6 | 51,561.2 | 56,587.4 | 64,115.3 | 228,491.4 | 184,400.0 | +23.9% |
| Research & development | 25,831.0 | 24,264.3 | 25,602.7 | 29,152.1 | 104,850.1 | 74,463.0 | +40.8% |
| Sales & marketing | 10,243.4 | 9,662.8 | 10,518.4 | 11,125.7 | 41,550.3 | 33,028.0 | +25.8% |
| General & administrative | 6,894.4 | 6,790.2 | 7,290.1 | 7,841.7 | 28,816.5 | 22,231.0 | +29.6% |
| Total costs and expenses | 99,196.5 | 92,278.5 | 99,998.5 | 112,234.8 | 403,708.3 | 314,122.0 | +28.5% |
| Operating income | 46,904.1 | 51,613.1 | 54,486.2 | 53,939.9 | 206,943.3 | 156,976.0 | +31.8% |

Operating margin: **33.9%** next 4 quarters vs **33.3%** in the prior 4 reported quarters.

## Cost assumptions as resolved

| Cost line | Method | Trend (pp YoY) | Source |
|---|---|---:|---|
| Cost of revenues | same_quarter_ly_plus_trend | -1.72 | auto: mean YoY change, last 4 quarters |
| Research & development | same_quarter_ly_plus_trend | +1.36 | auto: mean YoY change, last 4 quarters |
| Sales & marketing | same_quarter_ly_plus_trend | -0.21 | auto: mean YoY change, last 4 quarters |
| General & administrative | ttm_ratio |  | n/a |

Planned cost ratios (% of total revenue):

|  | Cost of revenues | Research & development | Sales & marketing | General & administrative |
|---|---:|---:|---:|---:|
| 2026Q4 | 38.49% | 17.68% | 7.01% | 4.72% |
| 2027Q1 | 35.83% | 16.86% | 6.72% | 4.72% |
| 2027Q2 | 36.63% | 16.57% | 6.81% | 4.72% |
| 2027Q3 | 38.58% | 17.54% | 6.70% | 4.72% |

## Memo: depreciation outlook (not in the cost plan)

Depreciation next quarter = this quarter's depreciation + k x this quarter's capex, with k = 0.0198
(mean of the last 4 quarters) and capex held at the 2026Q3 level ($51,355M per quarter).
This is the capex-to-depreciation link from experiment E2. Its pass-through into the cost-of-revenues ratio
was not adopted, because the fitted coefficient had the wrong sign (see [`experiments.md`](experiments.md)).

|  | 2026Q4 | 2027Q1 | 2027Q2 | 2027Q3 | Next 4Q | Prior 4Q (actual) |
|---|---:|---:|---:|---:|---:|---:|
| Depreciation (capex-driven projection) | 9,388.1 | 10,407.1 | 11,426.2 | 12,445.3 | 43,666.7 | 27,995.0 |
| as % of planned revenue | 6.4 | 7.2 | 7.4 | 7.5 | 7.2 | 5.9 |
