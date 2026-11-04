# Methodology

## 1. Data

**Source.** Every number comes from Alphabet's 10-Q and 10-K filings on SEC EDGAR, 2017 onward: 41 filings, read from their XBRL instance documents (`src/fpa_forecast/sec_fetch.py`, `xbrl_parse.py`). The SEC `companyfacts` API is not used because it drops XBRL dimensions, and revenue by type and segment results are tagged with dimensions (`srt:ProductOrServiceAxis`, `us-gaap:StatementBusinessSegmentsAxis`).

**Mapping.** `dataset.py` maps tagged facts to the line items: revenue by type, segment revenue, cost lines, operating income, segment operating income, capex, depreciation (from 2023Q1) and revenue by region (US, EMEA, APAC, Other Americas). Mapping uses explicit rules: with explicit rules: concept + dimension members + the first filing date on which that definition applies. Member renames are aliased: `GoogleNetworkMembersPropertiesMember` → `GoogleNetworkMember`, and "Google other" → "Google subscriptions, platforms, and devices".

**Quarters.**
- 10-Qs report 3-month values directly.
- Q4 is not in any 10-Q, so Q4 = fiscal year (10-K) − nine months (Q3 10-Q).
- Capex is year-to-date in the cash-flow statement and is differenced into quarters.

**Vintages and restatements.**
- Each quarter appears in several filings, and the latest is used.
- A quarter is flagged `restated` if its latest value differs from the first reported value by more than $1M.
- When Q4 is derived, the fiscal-year and nine-month values must come from filings with no basis change between them. Restatement events are grouped into "basis regimes": a recast rolls through the next four filings' comparative columns. This stops a recast from landing entirely in one Q4. See [`restatements.md`](../restatements.md).

**Checks.** `tests/test_data.py` checks:
- no missing quarters;
- the four service lines sum to the separately tagged Google Services segment within $1M;
- segments + hedging = total revenue, where hedging is tagged on its own;
- revenue − costs = operating income;
- segment operating income sums to the total;
- known restatements are flagged;
- every row carries its source accession numbers.

## 2. SQL layer

DuckDB tables `fact_quarterly` (long), `dim_line` and `forecasts`, plus eight views in `sql/`:
- `pnl_quarterly`
- `revenue_mix`
- `opex_ratios`
- `segment_margin`
- `ttm_metrics`
- `forecast_vs_actual`
- `revenue_geography`
- `fx_exposure`

The SQL is plain ANSI: conditional aggregation, `LAG`, named windows and `NULLIF` division. The same statements run on BigQuery ([`bigquery/README.md`](../bigquery/README.md)). `sql/queries/backtest_accuracy.sql` recomputes the backtest metrics in SQL, and a test checks they match the Python metrics exactly.

## 3. Forecasting

**Target and hierarchy.** Quarterly revenue, 2019Q1 onward. That is the first quarter for which Alphabet published revenue by type on today's definitions.

```
Total revenue excl. hedging
├── Google Services ── Search & other · YouTube ads · Google Network · Subscriptions, platforms & devices
├── Google Cloud
└── Other Bets
```

Hedging gains/losses are FX-hedge results that can be negative and are not forecastable from history. They are planned at $0 and shown as their own variance line.

**Base models** (statsforecast, season length 4):
- `SeasonalNaive`
- `RandomWalkWithDrift`
- `AutoETS`
- `AutoARIMA`
- `AutoTheta`

Experiment E1 added three more:
- `AutoARIMA_d1`: AutoARIMA with at most one non-seasonal difference.
- `AutoARIMA_log`: AutoARIMA fit on log revenue. Forecasts and quantiles are back-transformed with exp(), so the point forecast is the median.
- `Combo`: the equal-weight mean of AutoETS, AutoARIMA and AutoTheta.

All are fit independently on each of the 10 nodes. Cloud and Other Bets each appear as both a segment node and a leaf.

**Interval kinds.**
- `model`: each model's own prediction intervals.
- `conformal`: split-conformal intervals from statsforecast (`ConformalIntervals(h, n_windows=2)`), calibrated on the model's rolling errors.

Point forecasts are identical for both kinds.

**Reconciliation** (hierarchicalforecast). The FP&A problem: each business line builds its own number bottom-up, leadership has a top-down number, and they rarely agree. Reconciliation makes them coherent: the lines add up to the segments, and the segments add up to the total. It also decides where the disagreement goes.
- **BottomUp.** Trust the line forecasts and add them up. This is the bottom-up build.
- **TopDown (forecast proportions).** Trust the total, and split it in the proportions the line forecasts imply. This is a top-down target allocated to the lines.
- **MinTrace (`mint_shrink`).** Adjust every node by the least amount needed, weighting each by how noisy its in-sample errors have been. It uses a shrinkage estimate of the error covariance, because 30-odd quarters is too short for a full covariance.

Intervals:
- BottomUp and MinTrace use the `normality` method.
- TopDown with forecast proportions supports only `bootstrap` intervals in hierarchicalforecast 1.5.3, so it uses those.

**Backtest.**
- Rolling origin with an expanding window, one-quarter steps, 12 forecast origins and horizons 1–4.
- The latest quarter (2026Q3) is excluded from the backtest. It is used only for the variance analysis, so model selection never sees it.

Metrics per series and per model × method:
- MAPE;
- WAPE (Σ|error| / Σ|actual|);
- MASE, scaled by the in-sample seasonal-naive mean absolute error up to each origin;
- empirical coverage of the 80% and 95% intervals;
- scaled interval score (MSIS): the interval width plus 2/α times any miss, divided by the MASE scale, then averaged over the 80% and 95% levels.

**Selection rules, fixed before each run** (see [`experiments.md`](experiments.md)):
- v0.1 took the lowest mean MASE across the 8 hierarchy series, among coherent forecasts only.
- Since E1, the selection has two stages:
  1. **Point forecast.** The incumbent (AutoARIMA + BottomUp) is kept unless a coherent challenger lowers mean MASE by at least 3%.
  2. **Intervals.** For the kept configuration, the interval kind with the lower mean MSIS.

Unreconciled `base` results are reported for reference only.

**Data vintage caveat.** The backtest uses today's restated data, not the data available at each origin (pseudo-out-of-sample). The revenue lines used here were not restated after the 2020 definition change, so the effect is nil for revenue.

## 4. FP&A outputs

**P&L.** Revenue lines come from the selected model. Costs are a share of total revenue, set in `assumptions.yaml`:
- **Same quarter last year + trend:** for cost of revenues, R&D and S&M. This keeps seasonality.
- **Trailing-4-quarter ratio:** for G&A, which is lumpy because of legal and regulatory charges.

Each trend is either an explicit number or `auto`, the mean year-over-year change in the ratio over the last 4 quarters. Every resolved value is printed in `reports/pnl_forecast.md`.

v0.1 used an explicit 0.0pp override for cost of revenues. Experiment E2 showed it overstated the ratio by about 1.5pp, so cost of revenues now uses `auto` as well.

**Depreciation memo.** Next quarter's depreciation = this quarter's depreciation + k × this quarter's capex.
- k is the mean ratio over the last 4 quarters.
- Capex is held at the last reported level.

This projection is reported next to the P&L and used as a risk sensitivity. Its pass-through into the cost-of-revenues ratio was tested in E2 and rejected: the fitted coefficient had the wrong sign.

**Track record (E3).** For each of the last 8 quarters, the whole P&L is forecast one quarter ahead with only prior data, and revenue and operating income are compared with actuals. Three configurations are shown:
- the production configuration;
- a fully real-time selection that uses only backtest results before each quarter;
- seasonal naive.

**Geography and FX.**
- Revenue by region, its share and growth come from SQL.
- Non-US share and hedging results relative to non-US revenue.
- A mechanical translation sensitivity: next-4-quarter revenue × trailing non-US share × 5%.

**Variance (holdout quarter).** The forecast for the holdout quarter is built only from data through the quarter before.
- *Revenue bridge:* forecast → each revenue line's variance → actual.
- *Operating income bridge:*
  - revenue variance × (1 − planned cost ratio) gives the flow-through;
  - each cost line's (planned ratio − actual ratio) × actual revenue gives the rate variances;
  - the steps add up exactly to the actual figure (asserted in code).

**Scenarios.**
- YoY growth of Google Cloud and Search & other shifts by ±5pp and ±2pp in every forecast quarter: scenario value = base forecast + prior-year actual × shift.
- Cost of revenues is variable (it stays at its planned ratio). R&D, S&M and G&A are fixed at base-case dollars inside the year.
- The sensitivity grid reports the 4-quarter operating margin over a 5 × 5 grid of the two shifts.

## 5. Limitations

- **History is short.** There are 31 quarters for the lines, 2019Q1–2026Q3, and each origin's training set has 18–29 points. Interval coverage is estimated from 42 forecasts per series and is noisy.
- **Interval calibration is uneven.** Since E1, the intervals over-cover most stable lines (several reach 100%), so they are conservative. Cloud still under-covers, because its growth accelerated through the backtest window.
- **The Cloud forecast is a statistical baseline.** It is not a view on capacity, pricing or contracts.
- **Simple cost model.** Costs are ratios to revenue. The capex → depreciation link is projected, but its pass-through into cost of revenues could not be estimated with a plausible sign from 10 year-over-year pairs. The plan and the depreciation memo therefore pull in different directions, and the executive summary quantifies the gap.
- **No constant-currency data.** Alphabet's constant-currency growth is not XBRL-tagged, so the FX sensitivity is mechanical translation only.
- **Segment operating income has basis breaks:**
  - 2022Q1, from the 2023 recast that covered only 2022;
  - 2023Q2, when the Brain team moved to Google DeepMind prospectively.
  
  Segment operating income is therefore reported, not forecast.
- **Excluded:** headcount (not in the XBRL facts) and non-operating items below operating income.
