"""Hierarchical revenue forecasting, reconciliation and rolling-origin backtest.

Hierarchy (USD millions, quarterly, 2019Q1 onward):

    Total revenue excl. hedging
    ├── Google Services ── Search & other, YouTube ads, Google Network,
    │                      Subscriptions, platforms & devices
    ├── Google Cloud
    └── Other Bets

Hedging gains/losses are FX-hedge results, not operating revenue; they are
planned at $0 (assumptions.yaml) and added back in the P&L.

Base models (statsforecast): SeasonalNaive, RandomWalkWithDrift, AutoETS,
AutoARIMA, AutoTheta. Each set of base forecasts is made coherent with
BottomUp, TopDown (forecast proportions) and MinTrace (mint_shrink).
"""
from __future__ import annotations

import json
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from hierarchicalforecast.core import HierarchicalReconciliation
from hierarchicalforecast.methods import BottomUp, MinTrace, TopDown
from hierarchicalforecast.utils import aggregate
from statsforecast import StatsForecast
from statsforecast.models import AutoARIMA, AutoETS, AutoTheta, RandomWalkWithDrift, SeasonalNaive
from statsforecast.utils import ConformalIntervals

SEASON = 4
LEVELS = [80, 95]
FIRST_QUARTER = "2019Q1"

SEGMENT_OF = {
    "search_other": "Google Services",
    "youtube_ads": "Google Services",
    "google_network": "Google Services",
    "subscriptions_platforms_devices": "Google Services",
    "google_cloud": "Google Cloud",
    "other_bets_revenue": "Other Bets",
}
BOTTOM_LINES = list(SEGMENT_OF)

# hierarchicalforecast unique_id -> dataset line key. Cloud and Other Bets have a
# single child, so their segment node and leaf node are the same series.
ID_TO_LINE = {
    "Alphabet": "total_revenue_ex_hedging",
    "Alphabet/Google Services": "google_services_revenue",
    "Alphabet/Google Cloud": "google_cloud",
    "Alphabet/Other Bets": "other_bets_revenue",
    **{f"Alphabet/Google Services/{k}": k for k in BOTTOM_LINES[:4]},
}
EVAL_LINES = list(ID_TO_LINE.values())

ORIGINAL_MODELS = ["SeasonalNaive", "RWD", "AutoETS", "AutoARIMA", "AutoTheta"]
# Added in experiment E1 (docs/experiments.md), after the first release showed narrow intervals.
EXTRA_MODELS = ["AutoARIMA_d1", "AutoARIMA_log", "Combo"]
MODEL_NAMES = ORIGINAL_MODELS + EXTRA_MODELS
COMBO_MEMBERS = ["AutoETS", "AutoARIMA", "AutoTheta"]
INTERVAL_KINDS = ["model", "conformal"]
CONFORMAL_WINDOWS = 2
METHOD_SUFFIX = {
    "BottomUp": "BottomUp",
    "TopDown": "TopDown_method-forecast_proportions",
    "MinT": "MinTrace_method-mint_shrink",
}
COHERENT_METHODS = list(METHOD_SUFFIX)

# Pre-registered rules (docs/experiments.md, E1).
SELECTION_METRIC = "mase"
INCUMBENT = ("AutoARIMA", "BottomUp")
MATERIALITY = 0.03  # a challenger must beat the incumbent's mean MASE by at least 3%


def base_models():
    return [SeasonalNaive(season_length=SEASON), RandomWalkWithDrift(), AutoETS(season_length=SEASON),
            AutoARIMA(season_length=SEASON), AutoTheta(season_length=SEASON),
            AutoARIMA(season_length=SEASON, max_d=1, alias="AutoARIMA_d1")]


def q_to_ds(q: str) -> pd.Timestamp:
    return pd.Period(q, freq="Q").end_time.normalize()


def ds_to_q(ds) -> str:
    return str(pd.Timestamp(ds).to_period("Q"))


@dataclass
class Hierarchy:
    Y: pd.DataFrame
    S: pd.DataFrame
    tags: dict


def build_hierarchy(wide: pd.DataFrame, first: str = FIRST_QUARTER, last: str | None = None) -> Hierarchy:
    w = wide.set_index("fiscal_quarter") if "fiscal_quarter" in wide.columns else wide
    w = w.loc[first:last] if last else w.loc[first:]
    rows = [dict(total="Alphabet", segment=SEGMENT_OF[line], line=line, ds=q_to_ds(q), y=float(v))
            for line in BOTTOM_LINES for q, v in w[line].items()]
    df = pd.DataFrame(rows)
    if df["y"].isna().any():
        raise ValueError("missing values in bottom-level series")
    Y, S, tags = aggregate(df, [["total"], ["total", "segment"], ["total", "segment", "line"]])
    return Hierarchy(Y, S, tags)


def _to_long(rec: pd.DataFrame, cutoff_ds, intervals: str) -> pd.DataFrame:
    out = []
    for model in MODEL_NAMES:
        variants = {"base": model, **{m: f"{model}/{s}" for m, s in METHOD_SUFFIX.items()}}
        for method, col in variants.items():
            if col not in rec.columns:
                continue
            part = rec[["unique_id", "ds"]].copy()
            part["model"], part["method"], part["intervals"] = model, method, intervals
            part["forecast"] = rec[col].to_numpy()
            for lv in LEVELS:
                part[f"lo_{lv}"] = rec.get(f"{col}-lo-{lv}", pd.Series(np.nan, index=rec.index)).to_numpy()
                part[f"hi_{lv}"] = rec.get(f"{col}-hi-{lv}", pd.Series(np.nan, index=rec.index)).to_numpy()
            out.append(part)
    long = pd.concat(out, ignore_index=True)
    long = long[long["unique_id"].isin(ID_TO_LINE)].copy()
    long["line"] = long["unique_id"].map(ID_TO_LINE)
    long["cutoff"] = ds_to_q(cutoff_ds)
    long["fiscal_quarter"] = long["ds"].map(ds_to_q)
    cut = pd.Period(ds_to_q(cutoff_ds), freq="Q")
    long["horizon"] = long["fiscal_quarter"].map(lambda q: (pd.Period(q, freq="Q") - cut).n)
    return long.drop(columns=["unique_id"])


def _interval_cols(name: str) -> list[str]:
    return [name] + [f"{name}-{b}-{lv}" for lv in LEVELS for b in ("lo", "hi")]


def _base_forecasts(train: pd.DataFrame, horizon: int, conformal: bool):
    """Base forecasts for every candidate model. Returns (forecasts, in-sample fitted or None)."""
    kw = {"prediction_intervals": ConformalIntervals(h=horizon, n_windows=CONFORMAL_WINDOWS)} if conformal else {}
    sf = StatsForecast(models=base_models(), freq="QE")
    fc = sf.forecast(df=train, h=horizon, level=LEVELS, fitted=not conformal, **kw)
    ins = None if conformal else sf.forecast_fitted_values()
    # log-scale AutoARIMA, back-transformed (median); quantiles map through exp() unchanged
    sfl = StatsForecast(models=[AutoARIMA(season_length=SEASON, alias="AutoARIMA_log")], freq="QE")
    fl = sfl.forecast(df=train.assign(y=np.log(train["y"])), h=horizon, level=LEVELS, fitted=not conformal, **kw)
    cols = _interval_cols("AutoARIMA_log")
    fl[cols] = np.exp(fl[cols])
    fc = fc.merge(fl[["unique_id", "ds"] + cols], on=["unique_id", "ds"])
    if ins is not None:
        il = sfl.forecast_fitted_values()
        il[cols] = np.exp(il[cols])
        ins = ins.merge(il[["unique_id", "ds"] + cols], on=["unique_id", "ds"])
    # equal-weight combination; bounds are the mean of member bounds
    for frame in [fc] + ([ins] if ins is not None else []):
        for suffix in [""] + [f"-{b}-{lv}" for lv in LEVELS for b in ("lo", "hi")]:
            frame[f"Combo{suffix}"] = frame[[f"{m}{suffix}" for m in COMBO_MEMBERS]].mean(axis=1)
    return fc, ins


def forecast_at(h: Hierarchy, cutoff: str, horizon: int, interval_kinds=INTERVAL_KINDS) -> pd.DataFrame:
    """Fit on data up to and including `cutoff`; return base + reconciled forecasts (long).

    Point forecasts do not depend on the interval kind; only the bounds differ.
    """
    cutoff_ds = q_to_ds(cutoff)
    train = h.Y[h.Y["ds"] <= cutoff_ds]
    out = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fc_model, ins = _base_forecasts(train, horizon, conformal=False)
        # forecast_proportions only supports bootstrap intervals in hierarchicalforecast
        rec_td = HierarchicalReconciliation([TopDown(method="forecast_proportions")]).reconcile(
            Y_hat_df=fc_model, Y_df=ins, S_df=h.S, tags=h.tags, level=LEVELS, intervals_method="bootstrap")
        td_cols = [c for c in rec_td.columns if "TopDown" in c]
        for kind in interval_kinds:
            fc = fc_model if kind == "model" else _base_forecasts(train, horizon, conformal=True)[0]
            rec = HierarchicalReconciliation([BottomUp(), MinTrace(method="mint_shrink")]).reconcile(
                Y_hat_df=fc, Y_df=ins, S_df=h.S, tags=h.tags, level=LEVELS, intervals_method="normality")
            rec = rec.merge(rec_td[["unique_id", "ds"] + td_cols], on=["unique_id", "ds"], how="left")
            out.append(_to_long(rec, cutoff_ds, kind))
    return pd.concat(out, ignore_index=True)


def mase_scale(h: Hierarchy, cutoff: str) -> pd.Series:
    """In-sample mean absolute seasonal difference per series, up to the cutoff."""
    train = h.Y[h.Y["ds"] <= q_to_ds(cutoff)].sort_values("ds")
    scale = train.groupby("unique_id")["y"].apply(lambda s: s.diff(SEASON).abs().mean())
    return scale[scale.index.isin(ID_TO_LINE)].rename(index=ID_TO_LINE)


def backtest(h: Hierarchy, cutoffs: list[str], horizon: int = 4, last_actual: str | None = None) -> pd.DataFrame:
    """Rolling-origin, expanding-window backtest. Targets after `last_actual` are dropped."""
    actual = h.Y[h.Y["unique_id"].isin(ID_TO_LINE)].assign(
        line=lambda d: d["unique_id"].map(ID_TO_LINE), fiscal_quarter=lambda d: d["ds"].map(ds_to_q))
    actual = actual[["line", "fiscal_quarter", "y"]].rename(columns={"y": "actual"})
    frames = []
    for c in cutoffs:
        fc = forecast_at(h, c, horizon)
        fc = fc.merge(actual, on=["line", "fiscal_quarter"], how="inner")
        if last_actual:
            fc = fc[fc["fiscal_quarter"] <= last_actual]
        fc["mase_scale"] = fc["line"].map(mase_scale(h, c))
        frames.append(fc)
    return pd.concat(frames, ignore_index=True)


def score(bt: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    e = bt["actual"] - bt["forecast"]
    y = bt["actual"]
    isc = []
    for lv in LEVELS:
        a = 1 - lv / 100
        lo, hi = bt[f"lo_{lv}"], bt[f"hi_{lv}"]
        isc.append((hi - lo) + (2 / a) * (lo - y).clip(lower=0) + (2 / a) * (y - hi).clip(lower=0))
    msis = ((isc[0] + isc[1]) / 2) / bt["mase_scale"]
    d = bt.assign(abs_err=e.abs(), ape=(e.abs() / bt["actual"].abs()), scaled=e.abs() / bt["mase_scale"],
                  msis=msis,
                  in_80=bt["actual"].between(bt["lo_80"], bt["hi_80"]).where(bt["lo_80"].notna()),
                  in_95=bt["actual"].between(bt["lo_95"], bt["hi_95"]).where(bt["lo_95"].notna()))
    g = d.groupby(by)
    out = pd.DataFrame({
        "mape": g["ape"].mean(),
        "wape": g["abs_err"].sum() / g["actual"].apply(lambda s: s.abs().sum()),
        "mase": g["scaled"].mean(),
        "coverage_80": g["in_80"].mean(),
        "coverage_95": g["in_95"].mean(),
        "msis": g["msis"].mean(),
        "n": g.size(),
    })
    return out.reset_index()


KEYS = ["model", "method", "intervals"]


def evaluate(bt: pd.DataFrame) -> dict[str, pd.DataFrame]:
    per_line = score(bt, KEYS + ["line"])
    overall = (per_line.groupby(KEYS)
               .agg(mean_mase=("mase", "mean"), mean_mape=("mape", "mean"), mean_wape=("wape", "mean"),
                    mean_msis=("msis", "mean"), coverage_80=("coverage_80", "mean"),
                    coverage_95=("coverage_95", "mean"))
               .reset_index())
    total = per_line[per_line["line"] == "total_revenue_ex_hedging"].set_index(KEYS)
    overall = overall.join(total[["wape", "mase", "mape"]].add_prefix("total_"), on=KEYS)
    by_h = score(bt, KEYS + ["horizon"])
    # Round before sorting so float noise across platforms cannot reorder ties (e.g. SeasonalNaive,
    # whose point forecasts are identical under every reconciliation method).
    overall = (overall.assign(_k=overall["mean_mase"].round(9), _m=overall["mean_msis"].round(9))
               .sort_values(["_k", "model", "method", "_m", "intervals"]).drop(columns=["_k", "_m"])
               .reset_index(drop=True))
    return {"per_line": per_line, "overall": overall, "by_horizon": by_h}


def select(overall: pd.DataFrame, incumbent: tuple[str, str] | None = INCUMBENT,
           materiality: float = MATERIALITY) -> dict:
    """Pre-registered two-stage rule (docs/experiments.md, E1).

    1. Point forecast: lowest mean MASE among coherent combinations; the incumbent is kept unless the
       best challenger is at least `materiality` lower. `incumbent=None` = plain lowest-MASE choice.
    2. Intervals: for the kept combination, the interval kind with the lower mean MSIS.
    """
    pts = overall[overall["method"].isin(COHERENT_METHODS) & (overall["intervals"] == "model")]
    pts = pts.assign(_k=pts["mean_" + SELECTION_METRIC].round(9)).sort_values(["_k", "model", "method"])
    best = pts.iloc[0]
    log = {"best_model": best["model"], "best_method": best["method"], "best_mean_mase": float(best["mean_mase"])}
    model, method = best["model"], best["method"]
    if incumbent is not None:
        inc = pts[(pts["model"] == incumbent[0]) & (pts["method"] == incumbent[1])].iloc[0]
        log.update(incumbent_model=incumbent[0], incumbent_method=incumbent[1],
                   incumbent_mean_mase=float(inc["mean_mase"]), materiality=materiality)
        if not best["mean_mase"] <= (1 - materiality) * inc["mean_mase"]:
            model, method = incumbent
    cand = overall[(overall["model"] == model) & (overall["method"] == method)].set_index("intervals")
    log.update({f"msis_{k}": float(cand.loc[k, "mean_msis"]) for k in cand.index})
    intervals = cand["mean_msis"].astype(float).round(9).sort_values(kind="stable").index[0]
    return {"model": model, "method": method, "intervals": intervals,
            "rule": "lowest mean MASE across the 8 hierarchy series (coherent forecasts; the incumbent "
                    f"{INCUMBENT[0]} + {INCUMBENT[1]} is kept unless beaten by >= {MATERIALITY:.0%}), then the "
                    "interval kind with the lower mean scaled interval score",
            "decision_log": log}


def pick(fc: pd.DataFrame, choice: dict) -> pd.DataFrame:
    """Rows of a long forecast frame that belong to the chosen configuration."""
    m = (fc["model"] == choice["model"]) & (fc["method"] == choice["method"])
    if "intervals" in fc.columns:
        m &= fc["intervals"] == choice.get("intervals", "model")
    return fc[m]


def run(wide: pd.DataFrame, holdout: str, backtest_cutoffs: list[str], live_horizon: int = 8) -> dict:
    """Backtest (targets < holdout), select, then holdout forecast and live forecast."""
    last_q = wide["fiscal_quarter"].max() if "fiscal_quarter" in wide.columns else wide.index.max()
    h_all = build_hierarchy(wide)
    prev = str(pd.Period(holdout, freq="Q") - 1)
    bt = backtest(h_all, backtest_cutoffs, horizon=4, last_actual=prev)
    ev = evaluate(bt)
    choice = select(ev["overall"])
    hold = forecast_at(h_all, prev, horizon=1)
    live = forecast_at(h_all, last_q, horizon=live_horizon)
    return {"backtest": bt, "eval": ev, "choice": choice, "holdout": hold, "live": live,
            "meta": {"holdout_quarter": holdout, "backtest_cutoffs": backtest_cutoffs, "last_actual": last_q,
                     "first_quarter": FIRST_QUARTER}}


def default_cutoffs(holdout: str, n_windows: int = 12) -> list[str]:
    """Cutoffs whose one-step-ahead targets are the n quarters before the holdout."""
    end = pd.Period(holdout, freq="Q") - 2
    return [str(end - i) for i in range(n_windows - 1, -1, -1)]


def forecasts_table(result: dict) -> pd.DataFrame:
    """Rows for the SQL `forecasts` table."""
    parts = []
    for run_type, df in [("backtest", result["backtest"]), ("holdout", result["holdout"]), ("live", result["live"])]:
        d = df.copy()
        d["run_type"] = run_type
        d["model"] = config_label(d)
        parts.append(d)
    out = pd.concat(parts, ignore_index=True)
    return out[["run_type", "model", "cutoff", "fiscal_quarter", "horizon", "line",
                "forecast", "lo_80", "hi_80", "lo_95", "hi_95"]]


def config_label(d: pd.DataFrame) -> pd.Series:
    """'AutoARIMA/BottomUp', or 'AutoARIMA/BottomUp/conformal' for conformal intervals."""
    return d["model"] + "/" + d["method"] + np.where(d["intervals"] == "conformal", "/conformal", "")


def save_choice(choice: dict, path) -> None:
    path.write_text(json.dumps(choice, indent=2))
