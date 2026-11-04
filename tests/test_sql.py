"""The SQL views agree with the underlying facts."""
import pandas as pd
import pytest

from fpa_forecast import sql_layer

VIEWS = ["pnl_quarterly", "revenue_mix", "opex_ratios", "segment_margin", "ttm_metrics", "forecast_vs_actual"]


@pytest.fixture(scope="module")
def con():
    c = sql_layer.build(":memory:")
    yield c
    c.close()


@pytest.mark.parametrize("view", VIEWS)
def test_view_exists(con, view):
    con.execute(f"SELECT * FROM {view} LIMIT 1")


def test_pnl_identity(con):
    df = sql_layer.query(con, "SELECT * FROM pnl_quarterly")
    lines = df[["cost_of_revenues", "research_development", "sales_marketing", "general_administrative", "ec_fines"]].sum(axis=1)
    assert ((lines - df.total_costs_expenses).abs() <= 1).all()
    assert ((df.total_revenue - df.total_costs_expenses - df.operating_income).abs() <= 1).all()
    assert len(df) >= 39


def test_revenue_mix_shares_sum_to_one(con):
    df = sql_layer.query(con, """
        SELECT fiscal_quarter, SUM(share_of_total) AS s, COUNT(*) AS n
        FROM revenue_mix GROUP BY fiscal_quarter HAVING COUNT(*) = 7""")
    assert len(df) >= 30
    assert ((df.s - 1).abs() < 1e-6).all()


def test_yoy_growth_matches_pandas(con):
    df = sql_layer.query(con, "SELECT fiscal_quarter, revenue, yoy_growth FROM revenue_mix WHERE line = 'google_cloud' ORDER BY fiscal_quarter")
    expected = df.revenue / df.revenue.shift(4) - 1
    pd.testing.assert_series_equal(df.yoy_growth, expected, check_names=False)


def test_ttm_revenue(con):
    pnl = sql_layer.query(con, "SELECT fiscal_quarter, total_revenue FROM pnl_quarterly ORDER BY fiscal_quarter")
    ttm = sql_layer.query(con, "SELECT fiscal_quarter, revenue_ttm FROM ttm_metrics ORDER BY fiscal_quarter")
    expected = pnl.total_revenue.rolling(4).sum()
    pd.testing.assert_series_equal(ttm.revenue_ttm, expected, check_names=False)


def test_segment_margin_sums_to_operating_income(con):
    df = sql_layer.query(con, """
        SELECT s.fiscal_quarter, SUM(s.operating_income) AS seg, MAX(p.operating_income) AS total
        FROM segment_margin s JOIN pnl_quarterly p USING (fiscal_quarter)
        GROUP BY s.fiscal_quarter""")
    assert ((df.seg - df.total).abs() <= 1).all()


def test_forecast_vs_actual_join(con):
    fc = pd.DataFrame([{"run_type": "backtest", "model": "x", "cutoff": "2026Q2", "fiscal_quarter": "2026Q3",
                        "horizon": 1, "line": "google_cloud", "forecast": 1.0, "lo_80": 0.0, "hi_80": 1e9,
                        "lo_95": 0.0, "hi_95": 1e9}])
    c = sql_layer.build(":memory:", forecasts=fc)
    df = sql_layer.query(c, "SELECT * FROM forecast_vs_actual")
    assert df.actual.notna().all() and (df.in_80 == 1).all()
    c.close()
