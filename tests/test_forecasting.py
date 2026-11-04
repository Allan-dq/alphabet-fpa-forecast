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
    for (model, kind, q), g in sub.groupby(["model", "intervals", "fiscal_quarter"]):
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
    seen = []
    real = F.StatsForecast.forecast

    def spy(self, *, df, **kw):
        seen.append(df["ds"].max())
        return real(self, df=df, **kw)

    monkeypatch.setattr(F.StatsForecast, "forecast", spy)
    F.forecast_at(hier, "2024Q2", horizon=1)
    assert len(seen) >= 4 and all(d == F.q_to_ds("2024Q2") for d in seen)


def test_log_model_and_combo(fc):
    log = fc[(fc.model == "AutoARIMA_log") & (fc.method == "base")]
    assert (log.forecast > 0).all() and log[["lo_80", "hi_95"]].notna().all().all()
    base = fc[(fc.method == "base") & (fc.intervals == "model")].pivot_table(
        index=["line", "fiscal_quarter"], columns="model", values="forecast")
    assert np.allclose(base["Combo"], base[F.COMBO_MEMBERS].mean(axis=1))


def test_point_forecasts_do_not_depend_on_interval_kind(fc):
    p = fc.pivot_table(index=["model", "method", "line", "fiscal_quarter"], columns="intervals", values="forecast")
    assert np.allclose(p["model"], p["conformal"])


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
    # all actuals inside both intervals -> interval score = width; scaled by 10, averaged over levels and rows
    assert s.msis == pytest.approx(((30 + 50) / 2 / 10 + (20 + 100) / 2 / 10) / 2)


def test_interval_score_penalises_misses():
    bt = pd.DataFrame({"model": "m", "method": "base", "line": "x", "actual": [100.0], "forecast": [100.0],
                       "mase_scale": [1.0], "lo_80": [101.0], "hi_80": [102.0], "lo_95": [100.0], "hi_95": [103.0]})
    s = F.score(bt, ["model"]).iloc[0]
    assert s.msis == pytest.approx(((1 + 2 / 0.2 * 1) + 3) / 2)


def _overall(rows):
    return pd.DataFrame(rows, columns=["model", "method", "intervals", "mean_mase", "mean_msis"])


def test_select_keeps_incumbent_unless_beaten_by_materiality():
    rows = [("AutoARIMA", "BottomUp", "model", 0.50, 5.0), ("AutoARIMA", "BottomUp", "conformal", 0.50, 4.0),
            ("X", "MinT", "model", 0.49, 3.0), ("X", "MinT", "conformal", 0.49, 6.0), ("Y", "base", "model", 0.10, 1.0)]
    ch = F.select(_overall(rows))
    assert (ch["model"], ch["method"], ch["intervals"]) == ("AutoARIMA", "BottomUp", "conformal")  # 2% < 3%
    rows[2] = ("X", "MinT", "model", 0.48, 3.0)
    ch = F.select(_overall(rows))
    assert (ch["model"], ch["method"], ch["intervals"]) == ("X", "MinT", "model")  # 4% >= 3%; base never eligible


def test_select_without_incumbent_is_plain_lowest_mase():
    rows = [("A", "BottomUp", "model", 0.50, 5.0), ("A", "BottomUp", "conformal", 0.50, 5.5),
            ("B", "TopDown", "model", 0.495, 9.0), ("B", "TopDown", "conformal", 0.495, 8.0)]
    ch = F.select(_overall(rows), incumbent=None)
    assert (ch["model"], ch["method"], ch["intervals"]) == ("B", "TopDown", "conformal")
