import numpy as np
import pandas as pd
import pytest

from fpa_forecast import fpa
from fpa_forecast.forecasting import config_label
from fpa_forecast.paths import PROCESSED_DIR, REPORTS_DIR


@pytest.fixture(scope="module")
def wide():
    return pd.read_csv(PROCESSED_DIR / "alphabet_quarterly_wide.csv")


@pytest.fixture(scope="module")
def assumptions():
    return fpa.load_assumptions()


def _fake_forecast(wide, quarters, scale=1.0):
    """A 'forecast' equal to the actuals (x scale), in the long format the FP&A code expects."""
    w = wide.set_index("fiscal_quarter")
    rows = [dict(model="M", method="BottomUp", line=ln, fiscal_quarter=q, forecast=w.loc[q, ln] * scale)
            for q in quarters for ln in fpa.BOTTOM_LINES]
    return pd.DataFrame(rows)


def test_plan_ratios_same_quarter_last_year(wide, assumptions):
    resolved = fpa.resolve_costs(wide, assumptions, "2025Q4")
    r = fpa.plan_ratios(wide, resolved, "2025Q4", ["2026Q1"])
    w = wide.set_index("fiscal_quarter")
    ratio = w["cost_of_revenues"] / w["total_revenue"] * 100
    trend = (ratio.loc["2025Q1":"2025Q4"].to_numpy() - ratio.loc["2024Q1":"2024Q4"].to_numpy()).mean()
    assert r.loc["2026Q1", "cost_of_revenues"] == pytest.approx(ratio.loc["2025Q1"] + trend)  # `auto` trend
    ttm = w.loc["2025Q1":"2025Q4", "general_administrative"].sum() / w.loc["2025Q1":"2025Q4", "total_revenue"].sum() * 100
    assert r.loc["2026Q1", "general_administrative"] == pytest.approx(ttm)


def test_auto_trend_is_mean_yoy_change(wide, assumptions):
    resolved = {r.line: r for r in fpa.resolve_costs(wide, assumptions, "2025Q4")}
    w = wide.set_index("fiscal_quarter")
    ratio = w["research_development"] / w["total_revenue"] * 100
    expected = (ratio.loc["2025Q1":"2025Q4"].to_numpy() - ratio.loc["2024Q1":"2024Q4"].to_numpy()).mean()
    assert resolved["research_development"].trend_pp == pytest.approx(expected)


def test_pnl_identity(wide, assumptions):
    qs = ["2026Q1", "2026Q2"]
    resolved = fpa.resolve_costs(wide, assumptions, "2025Q4")
    p = fpa.build_pnl(fpa.revenue_plan(_fake_forecast(wide, qs), {"model": "M", "method": "BottomUp"}, qs),
                      fpa.plan_ratios(wide, resolved, "2025Q4", qs))
    assert (p.total_revenue - p[fpa.REVENUE_LINES].sum(axis=1)).abs().max() < 1e-6
    assert (p.operating_income - (p.total_revenue - p[fpa.COST_LINES].sum(axis=1))).abs().max() < 1e-6


def test_variance_bridges_close(wide, assumptions):
    fc = _fake_forecast(wide, ["2026Q3"], scale=1.02)
    v = fpa.variance(wide, fc, {"model": "M", "method": "BottomUp"}, assumptions, "2026Q3")
    for bridge in (v["revenue_bridge"], v["oi_bridge"]):
        start, end = bridge.iloc[0].value, bridge.iloc[-1].value
        assert start + bridge[bridge.kind == "delta"].value.sum() == pytest.approx(end)
    assert v["table"].loc["total_revenue", "actual"] == wide.set_index("fiscal_quarter").loc["2026Q3", "total_revenue"]


def test_zero_shift_scenario_equals_base(wide, assumptions):
    qs = ["2026Q1", "2026Q2", "2026Q3"]
    resolved = fpa.resolve_costs(wide, assumptions, "2025Q4")
    ratios = fpa.plan_ratios(wide, resolved, "2025Q4", qs)
    rev = fpa.revenue_plan(_fake_forecast(wide, qs), {"model": "M", "method": "BottomUp"}, qs)
    base = fpa.build_pnl(rev, ratios)
    zero = fpa.scenario_pnl(rev, ratios, wide, {"google_cloud": 0.0}, assumptions["scenarios"]["cost_behavior"])
    pd.testing.assert_series_equal(base.operating_income, zero.operating_income)
    up = fpa.scenario_pnl(rev, ratios, wide, {"google_cloud": 5.0}, assumptions["scenarios"]["cost_behavior"])
    w = wide.set_index("fiscal_quarter")
    expected = sum(w.loc[str(pd.Period(q, freq="Q") - 4), "google_cloud"] * 0.05 for q in qs)
    assert up.google_cloud.sum() - base.google_cloud.sum() == pytest.approx(expected)


def test_depreciation_driver_definitions(wide):
    prm = fpa.depreciation_driver_params(wide, "2025Q4")
    w = wide.set_index("fiscal_quarter")
    dep, capex = w["depreciation"], w["capex"]
    k = np.mean([(dep[q] - dep[str(pd.Period(q, freq="Q") - 1)]) / capex[str(pd.Period(q, freq="Q") - 1)]
                 for q in ["2025Q1", "2025Q2", "2025Q3", "2025Q4"]])
    assert prm["k"] == pytest.approx(k)
    path = fpa.depreciation_path(prm, ["2026Q1", "2026Q2"])
    assert path["2026Q1"] == pytest.approx(dep["2025Q4"] + k * capex["2025Q4"])
    assert path["2026Q2"] == pytest.approx(path["2026Q1"] + k * capex["2025Q4"])  # capex held flat


def test_cost_driver_uses_no_future_data(wide):
    base = fpa.cost_driver_experiment(wide, ["2025Q3"])["table"].iloc[0]
    w = wide.set_index("fiscal_quarter").copy()
    w.loc["2025Q4":, ["depreciation", "capex", "cost_of_revenues"]] *= 3  # change only later quarters
    other = fpa.cost_driver_experiment(w.reset_index(), ["2025Q3"])["table"].iloc[0]
    for c in ["driver_pct", "incumbent_pct", "auto_trend_pct", "k", "s"]:
        assert other[c] == pytest.approx(base[c])


def test_scenario_keeps_depreciation_fixed_inside_cost_of_revenues(wide, assumptions):
    qs = ["2026Q1"]
    rev = fpa.revenue_plan(_fake_forecast(wide, qs), {"model": "M", "method": "BottomUp"}, qs)
    ratios = pd.DataFrame({c: [10.0] for c in fpa.COST_LINES}, index=qs)
    ratios["_cor_fixed_m"] = 1000.0
    base = fpa.build_pnl(rev, ratios)
    up = fpa.scenario_pnl(rev, ratios, wide, {"google_cloud": 10.0}, assumptions["scenarios"]["cost_behavior"])
    var_ratio = (base.cost_of_revenues - 1000.0) / base.total_revenue
    assert up.cost_of_revenues.iloc[0] == pytest.approx(up.total_revenue.iloc[0] * var_ratio.iloc[0] + 1000.0)


def test_sql_and_python_backtest_metrics_agree():
    """reports/sql/backtest_accuracy.csv (DuckDB) vs reports/backtest_per_line.csv (pandas)."""
    sql_path, py_path = REPORTS_DIR / "sql" / "backtest_accuracy.csv", REPORTS_DIR / "backtest_per_line.csv"
    if not sql_path.exists():
        pytest.skip("run `python run_pipeline.py` first")
    s = pd.read_csv(sql_path)
    p = pd.read_csv(py_path)
    p["model"] = config_label(p)
    m = s.merge(p, on=["model", "line"], suffixes=("_sql", "_py"))
    assert len(m) == len(p)
    for c in ["mape", "wape", "coverage_80", "coverage_95"]:
        assert (m[f"{c}_sql"] - m[f"{c}_py"]).abs().max() < 1e-9, c
