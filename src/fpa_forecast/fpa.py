"""FP&A outputs: next-4-quarter P&L, holdout variance bridge, scenarios.

All amounts are USD millions. Revenue comes from the selected forecast
(model + reconciliation method). Costs come from assumptions.yaml.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .forecasting import BOTTOM_LINES, pick
from .paths import REPO_ROOT

COST_LINES = ["cost_of_revenues", "research_development", "sales_marketing", "general_administrative"]
REVENUE_LINES = BOTTOM_LINES + ["hedging_gains_losses"]
LINE_NAMES = {
    "search_other": "Search & other",
    "youtube_ads": "YouTube ads",
    "google_network": "Google Network",
    "subscriptions_platforms_devices": "Subscriptions, platforms & devices",
    "google_cloud": "Google Cloud",
    "other_bets_revenue": "Other Bets",
    "hedging_gains_losses": "Hedging gains (losses)",
    "total_revenue": "Total revenues",
    "cost_of_revenues": "Cost of revenues",
    "research_development": "Research & development",
    "sales_marketing": "Sales & marketing",
    "general_administrative": "General & administrative",
    "total_costs": "Total costs and expenses",
    "operating_income": "Operating income",
}


def load_assumptions(path: Path | None = None) -> dict:
    return yaml.safe_load((path or REPO_ROOT / "assumptions.yaml").read_text())


def _w(wide: pd.DataFrame) -> pd.DataFrame:
    return wide.set_index("fiscal_quarter") if "fiscal_quarter" in wide.columns else wide


def _q(q: str, k: int) -> str:
    return str(pd.Period(q, freq="Q") + k)


# --------------------------------------------------------------------- costs
@dataclass
class ResolvedCost:
    line: str
    method: str
    trend_pp: float | None
    trend_source: str
    params: dict = field(default_factory=dict)


def depreciation_driver_params(wide: pd.DataFrame, as_of: str) -> dict:
    """Capex -> depreciation -> cost of revenues driver, estimated with data through `as_of` (E2).

    k: next quarter's depreciation = this quarter's depreciation + k x this quarter's capex;
       k = mean of (change in depreciation / prior-quarter capex) over the last 4 quarters.
    s: share of a change in depreciation intensity (depreciation / revenue) that shows up in the
       cost-of-revenues ratio; OLS slope through the origin of YoY change in cost-of-revenues % on
       YoY change in depreciation %, all pairs available at `as_of`; s = 1 if fewer than 4 pairs.
    """
    w = _w(wide).loc[:as_of]
    dep, capex, rev = w["depreciation"], w["capex"], w["total_revenue"]
    k_obs = (dep.diff() / capex.shift(1)).dropna().iloc[-4:]
    cor_pct = w["cost_of_revenues"] / rev * 100
    dep_pct = dep / rev * 100
    pairs = pd.concat([dep_pct - dep_pct.shift(4), cor_pct - cor_pct.shift(4)], axis=1, keys=["x", "y"]).dropna()
    s = float((pairs.x * pairs.y).sum() / (pairs.x ** 2).sum()) if len(pairs) >= 4 else 1.0
    return {"k": float(k_obs.mean()), "s": s, "n_pairs": int(len(pairs)), "n_k": int(len(k_obs)),
            "last_depreciation": float(dep.loc[as_of]), "last_capex": float(capex.loc[as_of])}


def depreciation_path(params: dict, quarters: list[str], capex_plan: str = "hold_last_quarter") -> pd.Series:
    if capex_plan != "hold_last_quarter":
        raise ValueError(f"unknown capex_plan {capex_plan!r}")
    d, cap, out = params["last_depreciation"], params["last_capex"], {}
    for q in quarters:
        d = d + params["k"] * cap  # capex is held at the last reported quarter
        out[q] = d
    return pd.Series(out)


def resolve_costs(wide: pd.DataFrame, assumptions: dict, as_of: str) -> list[ResolvedCost]:
    """Turn `auto` into numbers using data up to and including `as_of`."""
    w = _w(wide).loc[:as_of]
    ratio = w[COST_LINES].div(w["total_revenue"], axis=0) * 100
    out = []
    for line in COST_LINES:
        spec = assumptions["costs"][line]
        if spec["method"] == "ttm_ratio":
            out.append(ResolvedCost(line, "ttm_ratio", None, "n/a"))
            continue
        if spec["method"] == "depreciation_driver":
            prm = depreciation_driver_params(wide, as_of)
            prm["capex_plan"] = assumptions.get("capex_plan", "hold_last_quarter")
            out.append(ResolvedCost(line, "depreciation_driver", None,
                                    f"driver: k={prm['k']:.4f}, s={prm['s']:.2f} ({prm['n_pairs']} pairs)", prm))
            continue
        t = spec.get("trend_pp", "auto")
        if t == "auto":
            yoy = (ratio[line] - ratio[line].shift(4)).iloc[-4:]
            out.append(ResolvedCost(line, spec["method"], float(yoy.mean()), "auto: mean YoY change, last 4 quarters"))
        else:
            out.append(ResolvedCost(line, spec["method"], float(t), "explicit"))
    return out


def plan_ratios(wide: pd.DataFrame, resolved: list[ResolvedCost], as_of: str, quarters: list[str],
                revenue: pd.Series | None = None) -> pd.DataFrame:
    """Planned cost ratio (% of total revenue) per future quarter and cost line.

    `revenue` (planned total revenue by quarter) is needed by the depreciation driver. When that
    driver is used, column `_cor_fixed_m` holds the depreciation dollars inside cost of revenues,
    which do not flex with revenue in scenarios.
    """
    w = _w(wide).loc[:as_of]
    ratio = w[COST_LINES].div(w["total_revenue"], axis=0) * 100
    dep_pct = (w["depreciation"] / w["total_revenue"] * 100) if "depreciation" in w else None
    ttm = (w[COST_LINES].iloc[-4:].sum() / w["total_revenue"].iloc[-4:].sum()) * 100
    rows = {}
    for q in quarters:
        r = {}
        for rc in resolved:
            if rc.method == "ttm_ratio":
                r[rc.line] = ttm[rc.line]
            elif rc.method == "depreciation_driver":
                if revenue is None:
                    raise ValueError("the depreciation driver needs planned revenue")
                ly = _q(q, -4)
                if ly not in ratio.index:
                    raise ValueError(f"depreciation driver needs actuals for {ly}")
                dep_q = depreciation_path(rc.params, quarters, rc.params.get("capex_plan", "hold_last_quarter"))[q]
                r[rc.line] = ratio.loc[ly, rc.line] + rc.params["s"] * (dep_q / revenue[q] * 100 - dep_pct.loc[ly])
                r["_cor_fixed_m"] = rc.params["s"] * dep_q
            else:
                # same quarter last year; if that is itself a forecast quarter, step back again
                ly = _q(q, -4)
                k = 1
                while ly not in ratio.index:
                    ly = _q(q, -4 * (k + 1))
                    k += 1
                r[rc.line] = ratio.loc[ly, rc.line] + rc.trend_pp * k
        rows[q] = r
    out = pd.DataFrame(rows).T
    return out[COST_LINES + [c for c in out.columns if c.startswith("_")]]


def cost_driver_experiment(wide: pd.DataFrame, quarters: list[str]) -> dict:
    """E2 (docs/experiments.md): one-quarter-ahead cost-of-revenues ratio, incumbent vs driver.

    Actual revenue is the denominator, so revenue forecast error does not enter the comparison.
    """
    w = _w(wide)
    rows = []
    for q in quarters:
        as_of, ly = _q(q, -1), _q(q, -4)
        rev = w.loc[q, "total_revenue"]
        actual = w.loc[q, "cost_of_revenues"] / rev * 100
        ly_ratio = w.loc[ly, "cost_of_revenues"] / w.loc[ly, "total_revenue"] * 100
        hist = (w.loc[:as_of, "cost_of_revenues"] / w.loc[:as_of, "total_revenue"] * 100)
        auto = ly_ratio + (hist - hist.shift(4)).iloc[-4:].mean()
        prm = depreciation_driver_params(wide, as_of)
        dep_hat = prm["last_depreciation"] + prm["k"] * prm["last_capex"]
        driver = ly_ratio + prm["s"] * (dep_hat / rev * 100 - w.loc[ly, "depreciation"] / w.loc[ly, "total_revenue"] * 100)
        rows.append(dict(quarter=q, actual_pct=actual, incumbent_pct=ly_ratio, driver_pct=driver, auto_trend_pct=auto,
                         depreciation_forecast_m=dep_hat, depreciation_actual_m=w.loc[q, "depreciation"],
                         k=prm["k"], s=prm["s"], n_pairs=prm["n_pairs"]))
    df = pd.DataFrame(rows)
    mae = {c: float((df[f"{c}_pct"] - df["actual_pct"]).abs().mean()) for c in ["incumbent", "driver", "auto_trend"]}
    bias = {c: float((df[f"{c}_pct"] - df["actual_pct"]).mean()) for c in ["incumbent", "driver", "auto_trend"]}
    return {"table": df, "mae_pp": mae, "bias_pp": bias, "driver_wins": mae["driver"] < mae["incumbent"]}


# ---------------------------------------------------------------------- P&L
def revenue_plan(fc_long: pd.DataFrame, choice: dict, quarters: list[str], hedging: float = 0.0) -> pd.DataFrame:
    sel = pick(fc_long, choice)
    sel = sel[sel["line"].isin(BOTTOM_LINES) & sel["fiscal_quarter"].isin(quarters)]
    rev = sel.pivot(index="fiscal_quarter", columns="line", values="forecast").reindex(quarters)[BOTTOM_LINES]
    rev["hedging_gains_losses"] = hedging
    return rev


def build_pnl(revenue: pd.DataFrame, ratios: pd.DataFrame) -> pd.DataFrame:
    p = revenue.copy()
    p["total_revenue"] = p[REVENUE_LINES].sum(axis=1)
    for c in COST_LINES:
        p[c] = p["total_revenue"] * ratios.loc[p.index, c] / 100
    p["total_costs"] = p[COST_LINES].sum(axis=1)
    p["operating_income"] = p["total_revenue"] - p["total_costs"]
    p["operating_margin_pct"] = p["operating_income"] / p["total_revenue"] * 100
    return p


def actual_pnl(wide: pd.DataFrame, quarters: list[str]) -> pd.DataFrame:
    w = _w(wide).loc[quarters]
    p = w[REVENUE_LINES + ["total_revenue"] + COST_LINES].copy()
    p["total_costs"] = w["total_costs_expenses"]
    p["operating_income"] = w["operating_income"]
    p["operating_margin_pct"] = p["operating_income"] / p["total_revenue"] * 100
    return p


def pnl_table(pnl: pd.DataFrame, ly: pd.DataFrame | None = None) -> pd.DataFrame:
    """Lines as rows, quarters as columns, plus a 4-quarter total and YoY vs the year before."""
    lines = REVENUE_LINES + ["total_revenue"] + COST_LINES + ["total_costs", "operating_income"]
    t = pnl[lines].T
    t["Next 4Q"] = t.sum(axis=1)
    if ly is not None:
        prev = ly[lines].T.sum(axis=1)
        t["Prior 4Q (actual)"] = prev
        t["YoY %"] = (t["Next 4Q"] / prev - 1) * 100
    t.index = [LINE_NAMES[i] for i in t.index]
    return t


# ------------------------------------------------------------------ variance
def variance(wide: pd.DataFrame, fc_holdout: pd.DataFrame, choice: dict, assumptions: dict, quarter: str) -> dict:
    """Forecast (made with data through the prior quarter) vs actual for one quarter."""
    as_of = _q(quarter, -1)
    resolved = resolve_costs(wide, assumptions, as_of)
    rev = revenue_plan(fc_holdout, choice, [quarter], assumptions["revenue"]["hedging_gains_losses_m"])
    ratios = plan_ratios(wide, resolved, as_of, [quarter], revenue=rev[REVENUE_LINES].sum(axis=1))
    fc = build_pnl(rev, ratios)
    act = actual_pnl(wide, [quarter])
    f, a = fc.loc[quarter], act.loc[quarter]

    lines = REVENUE_LINES + ["total_revenue"] + COST_LINES + ["total_costs", "operating_income"]
    table = pd.DataFrame({"forecast": f[lines], "actual": a[lines]})
    table["variance"] = table["actual"] - table["forecast"]
    table["variance_pct"] = table["variance"] / table["forecast"].abs() * 100
    table.loc["operating_margin_pct"] = [f["operating_margin_pct"], a["operating_margin_pct"],
                                         a["operating_margin_pct"] - f["operating_margin_pct"], np.nan]

    rev_bridge = [("Forecast revenue", f["total_revenue"], "total")]
    rev_bridge += [(LINE_NAMES[ln], a[ln] - f[ln], "delta") for ln in REVENUE_LINES]
    rev_bridge += [("Actual revenue", a["total_revenue"], "total")]

    # Operating income bridge: volume flow-through + cost-rate variances.
    f_ratio = f[COST_LINES] / f["total_revenue"]
    a_ratio = a[COST_LINES] / a["total_revenue"]
    flow = (a["total_revenue"] - f["total_revenue"]) * (1 - f_ratio.sum())
    oi_bridge = [("Forecast operating income", f["operating_income"], "total"),
                 ("Revenue variance (flow-through)", flow, "delta")]
    oi_bridge += [(f"{LINE_NAMES[c]} rate", -(a_ratio[c] - f_ratio[c]) * a["total_revenue"], "delta") for c in COST_LINES]
    oi_bridge += [("Actual operating income", a["operating_income"], "total")]
    check = f["operating_income"] + sum(v for _, v, k in oi_bridge if k == "delta") - a["operating_income"]
    assert abs(check) < 1e-6, check

    return {"quarter": quarter, "as_of": as_of, "table": table,
            "revenue_bridge": pd.DataFrame(rev_bridge, columns=["step", "value", "kind"]),
            "oi_bridge": pd.DataFrame(oi_bridge, columns=["step", "value", "kind"]),
            "ratios": ratios, "resolved": resolved, "forecast_ratio": f_ratio * 100, "actual_ratio": a_ratio * 100}


def _sm(v: float) -> str:
    return f"{'+' if v >= 0 else '-'}${abs(v):,.0f}M"


def miss_drivers(var: dict, top: int = 3) -> list[str]:
    """Plain-language list of the biggest contributors to the revenue and OI variance."""
    out = []
    rb = var["revenue_bridge"]
    d = rb[rb.kind == "delta"].assign(absv=lambda x: x.value.abs()).sort_values("absv", ascending=False)
    total = var["table"].loc["total_revenue"]
    out.append(f"Revenue came in {_sm(total.variance)} ({total.variance_pct:+.1f}%) vs forecast.")
    for _, r in d.head(top).iterrows():
        out.append(f"{r.step}: {_sm(r.value)}")
    ob = var["oi_bridge"]
    od = ob[ob.kind == "delta"].assign(absv=lambda x: x.value.abs()).sort_values("absv", ascending=False)
    oi = var["table"].loc["operating_income"]
    out.append(f"Operating income came in {_sm(oi.variance)} ({oi.variance_pct:+.1f}%) vs forecast; "
               f"largest drivers: " + "; ".join(f"{r.step} {_sm(r.value)}" for _, r in od.head(top).iterrows()) + ".")
    return out


# ----------------------------------------------------------------- scenarios
def scenario_pnl(base_rev: pd.DataFrame, ratios: pd.DataFrame, wide: pd.DataFrame, shifts_pp: dict,
                 cost_behavior: dict) -> pd.DataFrame:
    """Shift YoY growth of selected lines by `shifts_pp` and re-cost the P&L."""
    w = _w(wide)
    base = build_pnl(base_rev, ratios)
    rev = base_rev.copy()
    for line, pp in shifts_pp.items():
        ly = pd.Series({q: w.loc[_q(q, -4), line] for q in rev.index})
        rev[line] = rev[line] + ly * pp / 100
    p = build_pnl(rev, ratios)
    if "_cor_fixed_m" in ratios.columns and cost_behavior.get("cost_of_revenues") == "variable":
        # depreciation follows capex, not revenue: only the rest of cost of revenues flexes
        fixed = ratios.loc[p.index, "_cor_fixed_m"]
        var_ratio = (base["cost_of_revenues"] - fixed) / base["total_revenue"]
        p["cost_of_revenues"] = p["total_revenue"] * var_ratio + fixed
    for c in COST_LINES:
        if cost_behavior.get(c) == "fixed":
            p[c] = base[c]
    p["total_costs"] = p[COST_LINES].sum(axis=1)
    p["operating_income"] = p["total_revenue"] - p["total_costs"]
    p["operating_margin_pct"] = p["operating_income"] / p["total_revenue"] * 100
    return p


def scenarios(base_rev: pd.DataFrame, ratios: pd.DataFrame, wide: pd.DataFrame, assumptions: dict) -> dict:
    sc = assumptions["scenarios"]
    behavior = sc["cost_behavior"]
    cases = {}
    for name, shifts in sc["cases"].items():
        p = scenario_pnl(base_rev, ratios, wide, shifts, behavior)
        cases[name] = {"revenue": p["total_revenue"].sum(), "operating_income": p["operating_income"].sum(),
                       "operating_margin_pct": p["operating_income"].sum() / p["total_revenue"].sum() * 100,
                       "google_cloud": p["google_cloud"].sum(), "search_other": p["search_other"].sum()}
    grid = sc["sensitivity_grid"]
    rows = []
    for s in grid["search_other"]:
        row = {}
        for c in grid["google_cloud"]:
            p = scenario_pnl(base_rev, ratios, wide, {"google_cloud": c, "search_other": s}, behavior)
            row[c] = p["operating_income"].sum() / p["total_revenue"].sum() * 100
        rows.append(pd.Series(row, name=s))
    sens = pd.DataFrame(rows)
    sens.index.name = "search_other_pp"
    sens.columns.name = "google_cloud_pp"
    return {"cases": pd.DataFrame(cases).T, "sensitivity": sens}
