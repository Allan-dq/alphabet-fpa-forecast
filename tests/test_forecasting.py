import numpy as np
import pandas as pd
import pytest

from fpa_forecast import forecasting as F
from fpa_forecast.paths import PROCESSED_DIR


@pytest.fixture(scope="module")
def wide():
    return pd.read_csv(PROCESSED_DIR / "alphabet_quarterly_wide.csv")


@pytest.fixture(scope="module")
def hier(wide):
    return F.build_hierarchy(wide, last="2025Q4")


@pytest.fixture(scope="module")
def fc(hier):
    return F.forecast_at(hier, "2025Q4", horizon=4)


def test_hierarchy_shape(hier):
    assert hier.S.shape == (10, 7)  # 10 nodes x (unique_id + 6 bottom series)
    assert hier.Y["ds"].min() == F.q_to_ds("2019Q1")
    total = hier.Y[hier.Y.unique_id == "Alphabet"].set_index("ds")["y"]
    bottoms = hier.Y[hier.Y.unique_id.str.count("/") == 2].groupby("ds")["y"].sum()
    assert np.allclose(total, bottoms)


@pytest.mark.parametrize("method", F.COHERENT_METHODS)
def test_reconciled_forecasts_are_coherent(fc, method):
    sub = fc[(fc.method == method)]
    for (model, q), g in sub.groupby(["model", "fiscal_quarter"]):
        g = g.set_index("line")["forecast"]
        services = g[["search_other", "youtube_ads", "google_network", "subscriptions_platforms_devices"]].sum()
        assert services == pytest.approx(g["google_services_revenue"], rel=1e-6)
        total = g[["google_services_revenue", "google_cloud", "other_bets_revenue"]].sum()
        assert total == pytest.approx(g["total_revenue_ex_hedging"], rel=1e-6), (model, method, q)


def test_forecast_horizons_and_no_leakage(fc):
    assert set(fc.horizon) == {1, 2, 3, 4}
    assert (fc.fiscal_quarter > "2025Q4").all()
    assert set(fc.fiscal_quarter) == {"2026Q1", "2026Q2", "2026Q3", "2026Q4"}


def test_training_window_ends_at_cutoff(hier, monkeypatch):
    seen = {}
    real = F.StatsForecast.forecast

    def spy(self, *, df, **kw):
        seen["max_ds"] = df["ds"].max()
        return real(self, df=df, **kw)

    monkeypatch.setattr(F.StatsForecast, "forecast", spy)
    F.forecast_at(hier, "2024Q2", horizon=1)
    assert seen["max_ds"] == F.q_to_ds("2024Q2")


def test_intervals_are_ordered(fc):
    sub = fc[fc.method.isin(["base", "BottomUp", "MinT"])].dropna(subset=["lo_95"])
    assert (sub.lo_95 <= sub.lo_80 + 1e-6).all() and (sub.lo_80 <= sub.forecast + 1e-6).all()
    assert (sub.forecast <= sub.hi_80 + 1e-6).all() and (sub.hi_80 <= sub.hi_95 + 1e-6).all()


def test_default_cutoffs():
    c = F.default_cutoffs("2026Q3", n_windows=12)
    assert c[0] == "2023Q2" and c[-1] == "2026Q1" and len(c) == 12


def test_score_on_known_values():
    bt = pd.DataFrame({
        "model": "m", "method": "base", "line": "x",
        "actual": [100.0, 200.0], "forecast": [110.0, 180.0], "mase_scale": [10.0, 10.0],
        "lo_80": [90.0, 190.0], "hi_80": [120.0, 210.0], "lo_95": [80.0, 150.0], "hi_95": [130.0, 250.0],
    })
    s = F.score(bt, ["model", "method", "line"]).iloc[0]
    assert s.mape == pytest.approx((0.10 + 0.10) / 2)
    assert s.wape == pytest.approx(30 / 300)
    assert s.mase == pytest.approx((1.0 + 2.0) / 2)
    assert s.coverage_80 == pytest.approx(1.0) and s.coverage_95 == pytest.approx(1.0)


def test_select_only_coherent():
    overall = pd.DataFrame({"model": ["a", "b", "c"], "method": ["base", "MinT", "BottomUp"],
                            "mean_mase": [0.1, 0.5, 0.4]})
    ch = F.select(overall)
    assert (ch["model"], ch["method"]) == ("c", "BottomUp")
