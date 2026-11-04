"""Data-quality tests on the committed quarterly dataset (no network needed)."""
import pandas as pd
import pytest

from fpa_forecast.paths import PROCESSED_DIR

TOL = 1.0  # USD millions
SERVICES = ["search_other", "youtube_ads", "google_network", "subscriptions_platforms_devices"]
COSTS = ["cost_of_revenues", "research_development", "sales_marketing", "general_administrative"]
SEGMENT_OI = ["oi_google_services", "oi_google_cloud", "oi_other_bets", "oi_alphabet_level"]

# line -> first quarter it must be available from (see restatements.md)
COVERAGE = {
    "total_revenue": "2017Q1", "other_bets_revenue": "2017Q1",
    **{c: "2017Q1" for c in COSTS + ["total_costs_expenses", "operating_income", "capex"]},
    **{c: "2019Q1" for c in SERVICES + ["google_cloud", "google_services_revenue", "hedging_gains_losses"]},
    **{c: "2020Q1" for c in SEGMENT_OI},
}


@pytest.fixture(scope="module")
def long():
    return pd.read_csv(PROCESSED_DIR / "alphabet_quarterly_long.csv")


@pytest.fixture(scope="module")
def wide(long):
    return long.pivot(index="fiscal_quarter", columns="line", values="value_m")


def _quarters(first: str, last: str) -> list[str]:
    return [str(p) for p in pd.period_range(first, last, freq="Q")]


def test_latest_quarter_is_present(wide):
    assert wide.index.max() >= "2026Q3"


@pytest.mark.parametrize("line,first", sorted(COVERAGE.items()))
def test_no_missing_quarters(wide, line, first):
    last = wide.index.max()
    series = wide.loc[first:last, line]
    missing = [q for q in _quarters(first, last) if q not in series.index or pd.isna(series.get(q))]
    assert not missing, f"{line} missing {missing}"


def test_service_lines_sum_to_tagged_services_segment(long, wide):
    tagged = long[(long.line == "google_services_revenue") & (long.derivation != "sum_of_service_lines")]
    qs = tagged.fiscal_quarter
    diff = (wide.loc[qs, SERVICES].sum(axis=1) - wide.loc[qs, "google_services_revenue"]).abs()
    assert len(qs) >= 20
    assert (diff <= TOL).all(), diff[diff > TOL]


def test_segments_plus_hedging_sum_to_total(long, wide):
    """Where hedging is tagged on its own, the identity is a real check."""
    tagged = long[(long.line == "hedging_gains_losses") & (long.derivation == "reported_3m")].fiscal_quarter
    tagged = list(tagged) + list(long[(long.line == "hedging_gains_losses") & (long.derivation == "fy_minus_9m")].fiscal_quarter)
    assert len(tagged) >= 4
    parts = wide.loc[tagged, ["google_services_revenue", "google_cloud", "other_bets_revenue", "hedging_gains_losses"]].sum(axis=1)
    diff = (parts - wide.loc[tagged, "total_revenue"]).abs()
    assert (diff <= TOL).all(), diff[diff > TOL]


def test_residual_hedging_is_small(long, wide):
    """Where hedging is the residual, it must still look like FX hedging (< 1.5% of revenue)."""
    resid = long[(long.line == "hedging_gains_losses") & (long.derivation == "residual_total_minus_segments")].fiscal_quarter
    share = (wide.loc[resid, "hedging_gains_losses"] / wide.loc[resid, "total_revenue"]).abs()
    assert (share < 0.015).all(), share[share >= 0.015]


def test_revenue_minus_costs_is_operating_income(wide):
    q = wide.dropna(subset=["total_revenue", "total_costs_expenses", "operating_income"]).index
    diff = (wide.loc[q, "total_revenue"] - wide.loc[q, "total_costs_expenses"] - wide.loc[q, "operating_income"]).abs()
    assert (diff <= TOL).all(), diff[diff > TOL]


def test_segment_operating_income_sums_to_total(wide):
    q = wide.dropna(subset=SEGMENT_OI).index
    assert len(q) >= 20
    diff = (wide.loc[q, SEGMENT_OI].sum(axis=1) - wide.loc[q, "operating_income"]).abs()
    assert (diff <= TOL).all(), diff[diff > TOL]


def test_ec_fines_only_in_2017_2019(wide):
    fines = wide["ec_fines"].dropna()
    assert set(fines.index) == {"2017Q2", "2018Q2", "2019Q1"}


def test_restated_flag_matches_first_vs_latest(long):
    assert long["restated"].isin([True, False]).all()
    has_first = long.dropna(subset=["first_value_m"])
    changed = (has_first.value_m - has_first.first_value_m).abs() > TOL
    assert (changed == has_first.restated).all()


@pytest.mark.parametrize("quarter,line", [
    ("2017Q1", "other_bets_revenue"),      # Nest moved into Google (Q1 2018)
    ("2018Q1", "general_administrative"),  # performance fees moved to OI&E (Q1 2019)
    ("2022Q1", "oi_google_services"),      # DeepMind / cost allocation recast (Q1 2023)
    ("2022Q4", "oi_other_bets"),
])
def test_known_restatements_are_flagged(long, quarter, line):
    row = long[(long.fiscal_quarter == quarter) & (long.line == line)]
    assert row["restated"].item() is True or row["restated"].item() == True  # noqa: E712


def test_every_row_has_a_source(long):
    assert long["source_accessions"].fillna("").str.len().gt(0).all()
    assert long["source_urls"].fillna("").str.startswith("https://www.sec.gov/").all()
