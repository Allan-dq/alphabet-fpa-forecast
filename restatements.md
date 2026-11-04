# Restatements and definition changes

Alphabet restates prior periods when it moves a business between segments or changes how it presents a cost. A forecast trained on a series that changed definition partway through will be wrong. This file lists every change that affects the lines in this repo.

## How restatements are detected

Every 10-Q and 10-K reports the current period plus comparatives. Most quarters are therefore reported in two or more filings ("vintages"). `src/fpa_forecast/dataset.py`:

1. collects every vintage of every (line, period) from the XBRL instance documents;
2. flags a quarter as `restated = True` when the latest vintage differs from the first by more than $1M;
3. records each change in `data/interim/restatement_events.csv` (filing date, accession, old and new value);
4. derives Q4 as fiscal year minus nine months, using only two filings on the same basis (no basis change between them), so a recast cannot leak into a single Q4.

The dataset always uses the latest available basis. `first_value_m` keeps the originally reported number for comparison.

## Changes found in the filings

| Effective filing | What changed (filing text) | Lines affected | Quarters restated in this dataset | Size of change |
|---|---|---|---|---|
| 10-Q Q1 2018 (0001652044-18-000016) | Nest joined Google's hardware team; Nest results moved from Other Bets into the Google segment ("Google other revenues"). | `other_bets_revenue` | 2017Q1–2017Q4 | −$112M to −$278M per quarter |
| 10-Q Q1 2019 (0001652044-19-000015) | Performance fees reclassified from general and administrative expenses to other income (expense), net, for all periods. | `general_administrative`, `total_costs_expenses`, `operating_income` | 2018Q1–2018Q4 | G&A −$18M to −$632M; operating income up by the same amount. 2017 quarters were not recast in any quarterly filing, so 2017 G&A is on the older basis. |
| 10-K FY2019 (0001652044-20-000008) | New revenue disclosure: Google Search & other, YouTube ads, Google Network, Google Cloud and Google other shown separately for the first time. Before this, "Google other" included Cloud. | All revenue-by-type lines | Definition break. Quarterly values on the new basis exist from 2019Q1 (via 2020 10-Q comparatives). | — |
| 10-K FY2020 (0001652044-21-000010) | Google Services and Google Cloud become separate reportable segments. | Segment revenue and segment operating income | Definition break. Quarterly segment operating income on this basis exists from 2020Q1. | — |
| 10-Q Q1 2023 (0001652044-23-000045) | DeepMind moved from Other Bets to Alphabet-level activities; cost allocation methodologies "updated and simplified". Prior periods recast. | `oi_google_services`, `oi_google_cloud`, `oi_other_bets`, `oi_alphabet_level` | 2022Q1–2022Q4 | Services −$879M to −$1,149M; Cloud +$225M to +$294M; Other Bets +$320M to +$394M; Alphabet-level +$191M to +$534M per quarter |
| Q2 2023 | Google Brain team combined with DeepMind as Google DeepMind and reported in Alphabet-level activities **prospectively** (no recast). | `oi_google_services`, `oi_alphabet_level` | Not restated. This shifts costs between the two lines from 2023Q2 on; the size is not disclosed, so it cannot be separated in the data | — |
| 10-K FY2023 (0001652044-24-000022) | "Google other" renamed "Google subscriptions, platforms, and devices". | `subscriptions_platforms_devices` | None: values unchanged across vintages (checked) | $0 |

### Basis breaks to keep in mind
- **Segment operating income:** 2020Q1–2021Q4 is on the pre-2023 allocation basis. 2022Q1 onward is on the 2023 basis, because 2021 quarters were never recast in a quarterly filing. Segment operating income is reported in this repo but **not forecast**, partly for this reason.
- **G&A and operating income:** 2017 is on the pre-2019 basis (performance fees inside G&A); 2018 onward excludes them.
- **Revenue by type:** only available on a consistent basis from 2019Q1. The FY2019 earnings release (8-K, Feb 2020) gave Q4 2018 on the new basis, but Q1–Q3 2018 were never published that way, so the forecasting hierarchy starts in 2019Q1. Total revenue is available from 2017Q1.

## 2024–2026 filings
Every filing from 2024 to 2026 contains the standard sentence that certain prior-period amounts were reclassified. **None of the lines tracked here changed by more than $1M between vintages in those filings.** If a reclassification happened in 2024–2025, it did not move revenue by type, segment revenue, cost lines, total or segment operating income, or capex by more than $1M in any quarter.

## Lines that are derived, not tagged
| Line | Periods | How |
|---|---|---|
| Q4 of any income-statement line | every year | fiscal year (10-K) − nine months (Q3 10-Q), same basis |
| `capex` Q2–Q4 | every year | difference of year-to-date cash-flow values |
| `hedging_gains_losses` | 2019Q1–2024Q1 (21 quarters) | total revenue − (Google Services + Google Cloud + Other Bets). Hedging is tagged on its own (`RevenueNotFromContractWithCustomer`) only in filings from mid-2025, which cover 2024Q2 onward. |
| `google_services_revenue` | 2019Q1–2019Q4 | sum of the four service lines (segment did not exist yet) |
| `ec_fines` | 2017Q2, 2018Q2, 2019Q1 | total costs and expenses − the four cost lines (the European Commission fines were a separate line in those years) |
