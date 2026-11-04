# Experiment log (pre-registered)

The first release selected **AutoARIMA + BottomUp** and showed two weaknesses:
- **Prediction intervals were too narrow:** 80% intervals covered 76.8% of outcomes, 95% intervals covered 86.6%, and Cloud's 80% interval covered only 19%.
- **The cost of revenues plan** relied on a judgment call ("hold the ratio flat") instead of a capex/depreciation driver.

The rules below were written and committed **before** any of these experiments were run. The git history shows this file landing before the results. Every candidate here was added *after* seeing the weaknesses above. That is disclosed, and it is why the bar for replacing the incumbent is set above zero.

## E1. Point model and intervals

**Candidates.** The five original base models, plus three more:
- `AutoARIMA_d1`: AutoARIMA with at most one non-seasonal difference. It cannot extrapolate an accelerating trend, the way a d=2 model does for Cloud.
- `AutoARIMA_log`: AutoARIMA fit on log revenue and back-transformed. This turns multiplicative growth into a linear trend.
- `Combo`: the equal-weight mean of AutoETS, AutoARIMA and AutoTheta. Its interval bounds are the mean of the members' bounds.

Each candidate is reconciled with BottomUp, TopDown (forecast proportions) and MinTrace (mint_shrink).

**Intervals.** Each base model gets two kinds of interval:
- the model's own (`model`);
- split-conformal intervals from statsforecast (`conformal`, `ConformalIntervals(h=4, n_windows=2)`). These are calibrated on the model's own recent rolling errors.

**Same backtest as before:** 12 origins (2023Q2–2026Q1), horizons 1–4, targets up to 2026Q2, and 2026Q3 held out.

**Interval metric.** Scaled interval score (MSIS):

`MSIS = [(u − l) + (2/α)(l − y)·1{y < l} + (2/α)(y − u)·1{y > u}] / MASE scale`

It is averaged over the 80% and 95% levels and over the 8 hierarchy series. Lower is better. It rewards narrow intervals but penalises misses.

**Decision rules:**
1. **Point forecast.** The incumbent (AutoARIMA + BottomUp) is replaced only if the best coherent challenger has a mean MASE **at least 3% lower**. With 24 combinations scored on 12 origins, smaller gaps are within noise.
2. **Intervals.** For the configuration kept in step 1, conformal intervals replace model intervals only if their mean MSIS is lower. Coverage at 80% and 95% is reported either way.

## E2. Cost of revenues: capex → depreciation driver

**Incumbent.** Cost of revenues as % of revenue = same quarter last year + 0.0pp.

**Challenger.** Cost of revenues as % of revenue = same quarter last year + s × (Δ depreciation intensity), where:
- depreciation intensity = depreciation / revenue, and Δ is its year-over-year change;
- next quarter's depreciation = this quarter's depreciation + k × this quarter's capex;
- k = mean of (Δ depreciation / prior-quarter capex) over the last 4 quarters;
- s = OLS slope, through the origin, of YoY Δ(cost-of-revenues %) on YoY Δ(depreciation %), using every pair available at the forecast origin. If fewer than 4 pairs exist, s = 1.

Everything is estimated only with data available at each origin. Depreciation uses the `us-gaap:Depreciation` tag, which has quarterly values from 2023Q1.

**Evaluation.** One-quarter-ahead forecasts of the cost-of-revenues ratio for each of the 8 quarters 2024Q4–2026Q3. Actual revenue is used as the denominator so that revenue error does not leak into the cost comparison.

**Decision rule.** The challenger replaces the incumbent if its mean absolute ratio error (pp) over the 8 quarters is lower.

## E3. Variance track record (descriptive, no decision)

For each quarter 2024Q4–2026Q3, the P&L for that quarter is forecast using only data through the previous quarter and compared with actuals, with revenue and operating income bridges.

Two revenue configurations are reported:
- **production:** the configuration kept after E1. Its selection used backtest targets through 2026Q2, so this is not fully out of sample.
- **real-time selection:** at each quarter, the coherent combination with the lowest mean MASE on backtest targets strictly before that quarter.

Seasonal naive is shown as the reference.

## Results

Results are written to `reports/experiments.md` by `python run_pipeline.py`.

## Amendments (logged after the results, never edited above)

- **2026-11-04, E2.** The pre-registered condition for adopting the depreciation driver was met: lower mean absolute error. The driver was **not adopted** anyway, because its fitted pass-through coefficient s is negative at every origin where it could be estimated. That would make a higher depreciation share *lower* the cost-of-revenues ratio, which means the regression is fitting the ratio's downward trend, not depreciation.
  - Instead, the cost-of-revenues assumption reverted from the v0.1 judgment override (+0.0pp) to the default `auto` trend rule that R&D and S&M use. The experiment showed the override overstated the ratio by about 1.5pp.
  - The `auto` rule also had the lowest error in E2. That was visible before the switch and is disclosed in `reports/experiments.md`.
