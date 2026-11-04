"""FP&A outputs: next-4-quarter P&L, holdout variance bridge, scenarios.

All amounts are USD millions. Revenue comes from the selected forecast
(model + reconciliation method). Costs come from assumptions.yaml.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .forecasting import BOTTOM_LINES
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
        t = spec.get("trend_pp", "auto")
        if t == "auto":
            yoy = (ratio[line] - ratio[line].shift(4)).iloc[-4:]
            out.append(ResolvedCost(line, spec["method"], float(yoy.mean()), "auto: mean YoY change, last 4 quarters"))
        else:
            out.append(ResolvedCost(line, spec["method"], float(t), "explicit"))
    return out


def plan_ratios(wide: pd.DataFrame, resolved: list[ResolvedCost], as_of: str, quarters: list[str]) -> pd.DataFrame:
    """Planned cost ratio (% of total revenue) per future quarter and cost line."""
    w = _w(wide).loc[:as_of]
    ratio = w[COST_LINES].div(w["total_revenue"], axis=0) * 100
    ttm = (w[COST_LINES].iloc[-4:].sum() / w["total_revenue"].iloc[-4:].sum()) * 100
    rows = {}
    for q in quarters:
        r = {}
        for rc in resolved:
            if rc.method == "ttm_ratio":
                r[rc.line] = ttm[rc.line]
            else:
                # same quarter last year; if that is itself a forecast quarter, step back again
                ly = _q(q, -4)
                k = 1
                while ly not in ratio.index:
                    ly = _q(q, -4 * (k + 1))
                    k += 1
                r[rc.line] = ratio.loc[ly, rc.line] + rc.trend_pp * k
        rows[q] = r
    return pd.DataFrame(rows).T[COST_LINES]


# ---------------------------------------------------------------------- P&L
def revenue_plan(fc_long: pd.DataFrame, choice: dict, quarters: list[str], hedging: float = 0.0) -> pd.DataFrame:
    sel = fc_long[(fc_long["model"] == choice["model"]) & (fc_long["method"] == choice["method"])
                  & fc_long["line"].isin(BOTTOM_LINES) & fc_long["fiscal_quarter"].isin(quarters)]
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
    ratios = plan_ratios(wide, resolved, as_of, [quarter])
    fc = build_pnl(revenue_plan(fc_holdout, choice, [quarter], assumptions["revenue"]["hedging_gains_losses_m"]), ratios)
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
