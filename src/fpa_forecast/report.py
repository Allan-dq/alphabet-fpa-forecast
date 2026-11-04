"""Write markdown/CSV reports, charts and the one-page executive summary."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import charts, fpa
from .forecasting import ID_TO_LINE, pick, q_to_ds  # noqa: F401
from .paths import FIG_DIR, REPORTS_DIR

DISCLAIMER = ("Independent educational project using public filings. Not investment advice. "
              "Not affiliated with Google/Alphabet.")

SERIES_NAMES = {
    "total_revenue_ex_hedging": "Total revenue excl. hedging",
    "google_services_revenue": "Google Services",
    "google_cloud": "Google Cloud",
    "other_bets_revenue": "Other Bets",
    "search_other": "Search & other",
    "youtube_ads": "YouTube ads",
    "google_network": "Google Network",
    "subscriptions_platforms_devices": "Subscriptions, platforms & devices",
}


# ------------------------------------------------------------------ helpers
def md_table(df: pd.DataFrame, fmt: dict | None = None, index: bool = True, default: str = "{:,.1f}") -> str:
    fmt = fmt or {}
    d = df.reset_index() if index else df.copy()
    if index and d.columns[0] == "index":
        d = d.rename(columns={"index": ""})
    cols = [str(c) for c in d.columns]
    align = ["---:" if pd.api.types.is_numeric_dtype(d[c]) and not pd.api.types.is_bool_dtype(d[c]) else "---"
             for c in d.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(align) + "|"]
    for _, r in d.iterrows():
        cells = []
        for c, v in zip(d.columns, r.values):
            if isinstance(v, (float, np.floating, int, np.integer)) and not isinstance(v, bool):
                cells.append("" if pd.isna(v) else fmt.get(c, default).format(v))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def pct(v: float, d: int = 1) -> str:
    return f"{v * 100:.{d}f}%"


def bn(v: float, d: int = 1) -> str:
    return f"${v / 1000:,.{d}f}B"


def sm(v: float) -> str:
    """Signed USD millions: +$28M / -$1,141M."""
    return f"{'+' if v >= 0 else '-'}${abs(v):,.0f}M"


# ----------------------------------------------------------------- backtest
def backtest_report(result: dict) -> dict:
    ev, choice, meta = result["eval"], result["choice"], result["meta"]
    overall = ev["overall"].copy()
    overall.to_csv(REPORTS_DIR / "backtest_overall.csv", index=False)
    ev["per_line"].to_csv(REPORTS_DIR / "backtest_per_line.csv", index=False)
    ev["by_horizon"].to_csv(REPORTS_DIR / "backtest_by_horizon.csv", index=False)

    ref = {"model": "SeasonalNaive", "method": "base", "intervals": "model"}
    sel = pick(overall, choice).iloc[0]
    snaive = pick(overall, ref).iloc[0]
    drift = pick(overall, {**ref, "model": "RWD"}).iloc[0]
    pl = ev["per_line"]
    sel_lines = pick(pl, choice).set_index("line")
    sn_lines = pick(pl, ref).set_index("line")

    order = list(SERIES_NAMES)
    per_line = pd.DataFrame({
        "Series": [SERIES_NAMES[k] for k in order],
        "MAPE": [sel_lines.loc[k, "mape"] for k in order],
        "WAPE": [sel_lines.loc[k, "wape"] for k in order],
        "MASE": [sel_lines.loc[k, "mase"] for k in order],
        "Seasonal-naive WAPE": [sn_lines.loc[k, "wape"] for k in order],
        "Seasonal-naive MASE": [sn_lines.loc[k, "mase"] for k in order],
        "80% coverage": [sel_lines.loc[k, "coverage_80"] for k in order],
        "95% coverage": [sel_lines.loc[k, "coverage_95"] for k in order],
    })
    pfmt = {c: "{:.1%}" for c in ["MAPE", "WAPE", "Seasonal-naive WAPE", "80% coverage", "95% coverage"]}
    pfmt.update({c: "{:.2f}" for c in ["MASE", "Seasonal-naive MASE"]})

    top = overall.copy()
    top.insert(0, "rank", range(1, len(top) + 1))
    top = top[["rank", "model", "method", "intervals", "mean_mase", "mean_wape", "total_wape", "total_mase",
               "mean_msis", "coverage_80", "coverage_95"]]
    tfmt = {"mean_mase": "{:.3f}", "total_mase": "{:.3f}", "mean_wape": "{:.1%}", "total_wape": "{:.1%}",
            "mean_msis": "{:.2f}", "coverage_80": "{:.1%}", "coverage_95": "{:.1%}", "rank": "{:d}"}
    cut = meta["backtest_cutoffs"]
    n_points = int(sel_lines["n"].iloc[0])
    text = f"""# Backtest results

Rolling-origin backtest, expanding window, one-quarter steps. {len(cut)} forecast origins ({cut[0]} to {cut[-1]}),
horizons 1-4 quarters, targets up to {str(pd.Period(meta['holdout_quarter'], freq='Q') - 1)}. The latest quarter
({meta['holdout_quarter']}) is held out of the backtest and used only for the variance analysis. {n_points} scored
forecasts per series. Training data start in {meta['first_quarter']}.

**Selection rule (fixed before running, see `docs/experiments.md`):** {choice['rule']}.
**Selected:** `{choice['model']}` base forecasts reconciled with `{choice['method']}`, `{choice['intervals']}` prediction intervals.

## Headline

| | Selected ({choice['model']} + {choice['method']}, {choice['intervals']} intervals) | Seasonal naive | Random walk with drift |
|---|---:|---:|---:|
| Total revenue excl. hedging: WAPE | {pct(sel.total_wape)} | {pct(snaive.total_wape)} | {pct(drift.total_wape)} |
| Total revenue excl. hedging: MASE | {sel.total_mase:.2f} | {snaive.total_mase:.2f} | {drift.total_mase:.2f} |
| Mean MASE, 8 series | {sel.mean_mase:.2f} | {snaive.mean_mase:.2f} | {drift.mean_mase:.2f} |
| 80% interval coverage (all series) | {pct(sel.coverage_80)} | {pct(snaive.coverage_80)} | {pct(drift.coverage_80)} |
| 95% interval coverage (all series) | {pct(sel.coverage_95)} | {pct(snaive.coverage_95)} | {pct(drift.coverage_95)} |

## Selected model by series

{md_table(per_line, pfmt, index=False)}

## All model x reconciliation combinations (sorted by mean MASE)

`base` = unreconciled base forecasts, shown for reference; only coherent combinations were eligible for selection.
`intervals`: `model` = the model's own prediction intervals, `conformal` = split-conformal intervals (point forecasts are identical).
`mean_msis` = mean scaled interval score over the 80% and 95% levels (lower is better).

{md_table(top, tfmt, index=False)}

Files: `backtest_overall.csv`, `backtest_per_line.csv`, `backtest_by_horizon.csv`.
"""
    (REPORTS_DIR / "backtest_summary.md").write_text(text)
    return {"selected": sel, "snaive": snaive, "drift": drift, "per_line": per_line, "sel_lines": sel_lines}


# ---------------------------------------------------------------------- P&L
def pnl_report(wide, result, assumptions) -> dict:
    last = result["meta"]["last_actual"]
    n = assumptions["pnl_horizon_quarters"]
    qs = [str(pd.Period(last, freq="Q") + i) for i in range(1, n + 1)]
    ly_qs = [str(pd.Period(last, freq="Q") - i) for i in range(n - 1, -1, -1)]
    resolved = fpa.resolve_costs(wide, assumptions, last)
    rev = fpa.revenue_plan(result["live"], result["choice"], qs, assumptions["revenue"]["hedging_gains_losses_m"])
    ratios = fpa.plan_ratios(wide, resolved, last, qs, revenue=rev[fpa.REVENUE_LINES].sum(axis=1))
    pnl = fpa.build_pnl(rev, ratios)
    dep_prm = fpa.depreciation_driver_params(wide, last)
    dep_path = fpa.depreciation_path(dep_prm, qs, assumptions.get("capex_plan", "hold_last_quarter"))
    dep_ly = wide.set_index("fiscal_quarter").loc[ly_qs, "depreciation"]
    ly = fpa.actual_pnl(wide, ly_qs)
    table = fpa.pnl_table(pnl, ly)
    pnl.to_csv(REPORTS_DIR / "pnl_forecast.csv")

    res_rows = pd.DataFrame([{"Cost line": fpa.LINE_NAMES[r.line], "Method": r.method,
                              "Trend (pp YoY)": np.nan if r.trend_pp is None else r.trend_pp,
                              "Source": r.trend_source} for r in resolved])
    rat = ratios[fpa.COST_LINES].copy()
    rat.columns = [fpa.LINE_NAMES[c] for c in rat.columns]
    memo = pd.DataFrame({"Depreciation (capex-driven projection)": dep_path,
                         "as % of planned revenue": dep_path / pnl["total_revenue"] * 100}).T
    memo["Next 4Q"] = [dep_path.sum(), dep_path.sum() / pnl["total_revenue"].sum() * 100]
    memo["Prior 4Q (actual)"] = [dep_ly.sum(), dep_ly.sum() / ly["total_revenue"].sum() * 100]
    margin_next = pnl["operating_income"].sum() / pnl["total_revenue"].sum()
    margin_prev = ly["operating_income"].sum() / ly["total_revenue"].sum()
    text = f"""# Next-{n}-quarter P&L forecast ({qs[0]} to {qs[-1]})

USD millions. Revenue lines: `{result['choice']['model']}` + `{result['choice']['method']}` forecast with data through {last}.
Hedging gains (losses) planned at ${assumptions['revenue']['hedging_gains_losses_m']}M. Costs: `assumptions.yaml`.

{md_table(table, {'YoY %': '{:+.1f}%'})}

Operating margin: **{pct(margin_next)}** next {n} quarters vs **{pct(margin_prev)}** in the prior {n} reported quarters.

## Cost assumptions as resolved

{md_table(res_rows, {'Trend (pp YoY)': '{:+.2f}'}, index=False)}

Planned cost ratios (% of total revenue):

{md_table(rat, default='{:.2f}%')}

## Memo: depreciation outlook (not in the cost plan)

Depreciation next quarter = this quarter's depreciation + k x this quarter's capex, with k = {dep_prm['k']:.4f}
(mean of the last 4 quarters) and capex held at the {last} level (${dep_prm['last_capex']:,.0f}M per quarter).
This is the capex-to-depreciation link from experiment E2. Its pass-through into the cost-of-revenues ratio
was not adopted, because the fitted coefficient had the wrong sign (see [`experiments.md`](experiments.md)).

{md_table(memo, default='{:,.1f}')}
"""
    (REPORTS_DIR / "pnl_forecast.md").write_text(text)
    return {"pnl": pnl, "ly": ly, "ratios": ratios, "rev": rev, "resolved": resolved, "quarters": qs,
            "margin_next": margin_next, "margin_prev": margin_prev, "table": table,
            "dep_path": dep_path, "dep_ly": dep_ly, "dep_params": dep_prm}


# ----------------------------------------------------------------- variance
def variance_report(wide, result, assumptions) -> dict:
    q = assumptions["holdout_quarter"]
    var = fpa.variance(wide, result["holdout"], result["choice"], assumptions, q)
    t = var["table"].copy()
    t.to_csv(REPORTS_DIR / f"variance_{q}.csv")
    t.index = [fpa.LINE_NAMES.get(i, "Operating margin (%)") for i in t.index]
    drivers = fpa.miss_drivers(var)
    rb_sub = f"Forecast made with data through {var['as_of']} ({result['choice']['model']} + {result['choice']['method']}); hedging planned at $0"
    charts.waterfall(var["revenue_bridge"], f"{q} revenue: forecast vs actual, by revenue line", rb_sub + ". Y-axis does not start at zero.",
                     FIG_DIR / "variance_revenue_waterfall.png")
    charts.waterfall(var["oi_bridge"], f"{q} operating income: forecast vs actual",
                     "Revenue flow-through at the planned cost ratio, then cost-rate variances. Y-axis does not start at zero.",
                     FIG_DIR / "variance_oi_waterfall.png")
    fr = pd.DataFrame({"Planned % of revenue": var["forecast_ratio"], "Actual % of revenue": var["actual_ratio"]})
    fr["Difference (pp)"] = fr.iloc[:, 1] - fr.iloc[:, 0]
    fr.index = [fpa.LINE_NAMES[i] for i in fr.index]
    text = f"""# Variance analysis: {q} forecast vs actual

The {q} forecast uses only data through {var['as_of']}: revenue from the selected model (h = 1), costs from
`assumptions.yaml` resolved as of {var['as_of']}. {q} was not used for model selection.

{md_table(t, {'variance_pct': '{:+.1f}%', 'variance': '{:+,.1f}'})}

![Revenue bridge](figures/variance_revenue_waterfall.png)

![Operating income bridge](figures/variance_oi_waterfall.png)

## Cost ratios: plan vs actual

{md_table(fr, {'Difference (pp)': '{:+.2f}'}, default='{:.2f}%')}

## What drove the miss

""" + "\n".join(f"- {d}" for d in drivers) + "\n"
    (REPORTS_DIR / f"variance_{q}.md").write_text(text)
    var["drivers"] = drivers
    return var


# ---------------------------------------------------------------- scenarios
def scenario_report(wide, pnl_out, assumptions) -> dict:
    sc = fpa.scenarios(pnl_out["rev"], pnl_out["ratios"], wide, assumptions)
    cases = sc["cases"].copy()
    cases.to_csv(REPORTS_DIR / "scenarios.csv")
    sc["sensitivity"].to_csv(REPORTS_DIR / "sensitivity_operating_margin.csv")
    shifts = assumptions["scenarios"]["cases"]
    cases.insert(0, "Cloud growth shift (pp)", [shifts[c]["google_cloud"] for c in cases.index])
    cases.insert(1, "Search growth shift (pp)", [shifts[c]["search_other"] for c in cases.index])
    sens = sc["sensitivity"].copy()
    sens.index = [f"Search {v:+.1f}pp" for v in sens.index]
    sens.columns = [f"Cloud {v:+.1f}pp" for v in sens.columns]
    qs = pnl_out["quarters"]
    beh = assumptions["scenarios"]["cost_behavior"]
    text = f"""# Scenarios and sensitivity ({qs[0]} to {qs[-1]})

Scenarios shift the year-over-year growth of Google Cloud and Search & other in every forecast quarter
(scenario value = base forecast + prior-year actual x shift). Cost behavior: {', '.join(f'{fpa.LINE_NAMES[k]} {v}' for k, v in beh.items())}.

{md_table(cases, {'Cloud growth shift (pp)': '{:+.1f}', 'Search growth shift (pp)': '{:+.1f}', 'operating_margin_pct': '{:.2f}%'})}

## Operating margin sensitivity (next 4 quarters, %)

Rows: Search & other YoY growth shift. Columns: Google Cloud YoY growth shift.

{md_table(sens, default='{:.2f}%')}
"""
    (REPORTS_DIR / "scenarios.md").write_text(text)
    return sc


# ------------------------------------------------------------------- charts
def forecast_charts(wide, result) -> None:
    w = wide.set_index("fiscal_quarter")
    ch = result["choice"]
    live = result["live"]
    sel = pick(live, ch)
    first = result["meta"]["first_quarter"]

    def fc_for(line):
        return sel[sel.line == line].sort_values("fiscal_quarter")

    charts.forecast_chart(w.loc[first:, "total_revenue_ex_hedging"], fc_for("total_revenue_ex_hedging"),
                          "Alphabet quarterly revenue (excl. hedging): actual and 8-quarter forecast",
                          f"{ch['model']} base forecasts, {ch['method']} reconciliation, {ch['intervals']} intervals; shaded bands are 80% and 95%",
                          FIG_DIR / "forecast_total.png")
    keys = ["search_other", "youtube_ads", "google_network", "subscriptions_platforms_devices", "google_cloud", "other_bets_revenue"]
    charts.small_multiples({k: w.loc[first:, k] for k in keys}, {k: fc_for(k) for k in keys},
                           {k: SERIES_NAMES[k] for k in keys}, FIG_DIR / "forecast_lines.png",
                           "Revenue lines: actual and forecast (reconciled)")


# ------------------------------------------------------------ exec summary
def exec_summary(wide, con, result, bt, pnl_out, var, sc, assumptions, track=None, geo=None, hc=None) -> str:
    from . import sql_layer

    w = wide.set_index("fiscal_quarter")
    last = result["meta"]["last_actual"]
    qs = pnl_out["quarters"]
    pnl, ly = pnl_out["pnl"], pnl_out["ly"]
    rev_next, rev_prev = pnl["total_revenue"].sum(), ly["total_revenue"].sum()
    oi_next = pnl["operating_income"].sum()
    contrib = (pnl[fpa.BOTTOM_LINES].sum() - ly[fpa.BOTTOM_LINES].sum()).sort_values(ascending=False)
    growth = (pnl[fpa.BOTTOM_LINES].sum() / ly[fpa.BOTTOM_LINES].sum() - 1)
    ratios_prev = (ly[fpa.COST_LINES].sum() / rev_prev) * 100
    ratios_next = (pnl[fpa.COST_LINES].sum() / rev_next) * 100
    dr = (ratios_next - ratios_prev).sort_values(key=abs, ascending=False)

    ttm = sql_layer.query(con, f"SELECT * FROM ttm_metrics WHERE fiscal_quarter IN ('{last}', '{str(pd.Period(last, freq='Q') - 4)}') ORDER BY fiscal_quarter")
    seg = sql_layer.query(con, f"SELECT segment, operating_margin FROM segment_margin WHERE fiscal_quarter = '{last}'").set_index("segment")
    mix = sql_layer.query(con, f"SELECT line, share_of_total, yoy_growth, qoq_growth FROM revenue_mix WHERE fiscal_quarter = '{last}'").set_index("line")

    sel_lines = bt["sel_lines"]
    cloud_cov80 = sel_lines.loc["google_cloud", "coverage_80"]
    live = result["live"]
    ch = result["choice"]
    sel_live = pick(live, ch)
    cloud_end = sel_live[(sel_live.line == "google_cloud") & (sel_live.fiscal_quarter == qs[-1])].iloc[0]
    sens = sc["sensitivity"]
    cases = sc["cases"]
    one_pp_cor = rev_next * 0.01
    dep_next_pct = pnl_out["dep_path"].sum() / rev_next
    dep_prev_pct = pnl_out["dep_ly"].sum() / rev_prev
    dep_hit = (dep_next_pct - dep_prev_pct) * rev_next
    rv = var["table"]

    headline = (f"For the next four quarters ({qs[0]}-{qs[-1]}) we forecast revenue of **{bn(rev_next)}**, "
                f"{pct(rev_next / rev_prev - 1)} above the last four reported quarters, and operating income of "
                f"**{bn(oi_next)}** (margin **{pct(pnl_out['margin_next'])}** vs {pct(pnl_out['margin_prev'])}). "
                f"The model ({ch['model']} + {ch['method']} reconciliation) was chosen on a {len(result['meta']['backtest_cutoffs'])}-origin "
                f"backtest: total-revenue WAPE {pct(bt['selected'].total_wape)} vs {pct(bt['snaive'].total_wape)} for seasonal naive. "
                f"On the held-out quarter ({var['quarter']}) actual revenue differed from forecast by "
                f"{sm(rv.loc['total_revenue','variance'])} ({rv.loc['total_revenue','variance_pct']:+.1f}%) and operating income by "
                f"{sm(rv.loc['operating_income','variance'])} ({rv.loc['operating_income','variance_pct']:+.1f}%).")
    if track is not None:
        ts = track["summary"].set_index("config")
        prod, rt = ts.loc["production"], ts.loc["real-time selection"]
        headline += (f" Over the last 8 quarters, one-quarter-ahead revenue forecasts missed by {prod.mean_abs_revenue_var_pct:.1f}% on "
                     f"average ({rt.mean_abs_revenue_var_pct:.1f}% with fully real-time model selection; seasonal naive "
                     f"{ts.loc['seasonal naive'].mean_abs_revenue_var_pct:.1f}%).")

    names = fpa.LINE_NAMES
    drivers = []
    for k in contrib.index[:2]:
        drivers.append(f"**{names[k]}**: {bn(contrib[k])} of the {bn(rev_next - rev_prev)} revenue increase "
                       f"({pct(growth[k])} growth vs the prior four quarters).")
    c0 = dr.index[0]
    src = {r.line: r.trend_source.split(":")[0] for r in pnl_out["resolved"]}[c0]
    drivers.append(f"**Operating margin {pct(pnl_out['margin_next'])} vs {pct(pnl_out['margin_prev'])}**: the largest cost-ratio move is "
                   f"{names[c0]} at {ratios_next[c0]:.1f}% of revenue ({dr[c0]:+.1f}pp vs the prior four quarters; "
                   f"`{src}` trend in assumptions.yaml).")

    risks = [
        f"**Cloud is the swing factor and the least predictable line.** In the backtest only {pct(cloud_cov80, 0)} of Cloud "
        f"outcomes fell inside the 80% interval (growth kept accelerating). The {qs[-1]} Cloud forecast is {bn(cloud_end.forecast)} "
        f"with a 95% interval of {bn(cloud_end.lo_95)}-{bn(cloud_end.hi_95)}.",
        f"**Depreciation vs the cost plan.** Trailing-12-month capex reached {pct(ttm.iloc[-1].capex_intensity_ttm)} of revenue "
        f"in {last} (a year earlier: {pct(ttm.iloc[0].capex_intensity_ttm)}). With capex held at that level, depreciation rises to "
        f"{pct(dep_next_pct)} of revenue over the next four quarters from {pct(dep_prev_pct)}, while the cost plan extends the recent "
        f"{dr['cost_of_revenues']:+.1f}pp trend in the cost-of-revenues ratio. If the {(dep_next_pct - dep_prev_pct) * 100:+.1f}pp rise in "
        f"depreciation landed fully in cost of revenues, operating income would be about {bn(dep_hit)} lower (margin "
        f"{pct((oi_next - dep_hit) / rev_next)}).",
        f"**Search growth.** Search & other is {pct(mix.loc['search_other','share_of_total'])} of {last} revenue and came in "
        f"{rv.loc['search_other','variance_pct']:+.1f}% vs forecast in {var['quarter']}. The downside case (Search -2pp, Cloud -5pp) "
        f"lowers four-quarter revenue by {bn(cases.loc['base','revenue'] - cases.loc['downside','revenue'])} and margin to "
        f"{cases.loc['downside','operating_margin_pct']:.1f}%.",
    ]
    watch = [
        f"Google Cloud QoQ growth ({pct(mix.loc['google_cloud','qoq_growth'])} in {last}) and segment margin ({pct(seg.loc['Google Cloud','operating_margin'])}).",
        f"Search & other YoY growth ({pct(mix.loc['search_other','yoy_growth'])} in {last}).",
        f"Capex intensity, TTM ({pct(ttm.iloc[-1].capex_intensity_ttm)}) and cost of revenues as % of revenue.",
    ] + ([f"FX: non-US customers are {pct(geo['non_us_share_ttm'])} of revenue (TTM); a 5% stronger USD would lower "
          f"four-quarter revenue by about {bn(geo['fx5'])} before hedging."] if geo is not None else []) + (
        [f"Headcount {hc['employees']:,.0f} ({hc['yoy']:+.1%} YoY) and TTM revenue per employee "
         f"(${hc['rev_per_emp_m']:.2f}M) as opex grows with depreciation."] if hc is not None else []) + [
        f"Operating-margin range across the Cloud +/-5pp and Search +/-2pp grid: {sens.values.min():.1f}%-{sens.values.max():.1f}%.",
    ]
    sections = {"headline": headline, "drivers": drivers, "risks": risks, "watch": watch}

    md = f"""# Alphabet revenue and P&L outlook: {qs[0]} to {qs[-1]}

*Finance update, data through {last} (10-Q filed {result['meta'].get('last_filed', '')}). {DISCLAIMER}*

{headline}

![Forecast](figures/forecast_total.png)

**Top 3 drivers**
""" + "\n".join(f"{i}. {d}" for i, d in enumerate(drivers[:3], 1)) + """

**Top 3 risks**
""" + "\n".join(f"{i}. {d}" for i, d in enumerate(risks, 1)) + """

**Metrics to watch**
""" + "\n".join(f"- {d}" for d in watch) + """

Details: [P&L](pnl_forecast.md) · [backtest](backtest_summary.md) · [variance](variance_""" + var["quarter"] + """.md) · [track record and experiments](experiments.md) · [scenarios](scenarios.md) · [geography/FX](geography_fx.md) · [headcount](headcount.md) · [method](../docs/methodology.md)
"""
    (REPORTS_DIR / "exec_summary.md").write_text(md)
    (REPORTS_DIR / "exec_summary.json").write_text(json.dumps(sections, indent=2))
    exec_pdf(sections, qs, last, result["meta"].get("last_filed", ""))
    return md


def exec_pdf(sections: dict, qs: list[str], last: str, filed: str) -> None:
    import re

    from reportlab import rl_config
    from reportlab.lib.colors import HexColor

    rl_config.invariant = 1  # no timestamps or random IDs: identical bytes on every run
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import Image, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

    def rl(s: str) -> str:
        s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        return re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", s)

    ink, ink2 = HexColor(charts.INK), HexColor(charts.INK_2)
    base = ParagraphStyle("b", fontName="Helvetica", fontSize=8.6, leading=11, textColor=ink)
    h1 = ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=14, leading=17, spaceAfter=2)
    sub = ParagraphStyle("s", parent=base, fontSize=7.5, leading=9.5, textColor=ink2, spaceAfter=6)
    h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=9.6, leading=12, spaceBefore=5, spaceAfter=2)
    doc = SimpleDocTemplate(str(REPORTS_DIR / "exec_summary.pdf"), pagesize=letter, leftMargin=0.6 * inch,
                            rightMargin=0.6 * inch, topMargin=0.5 * inch, bottomMargin=0.45 * inch,
                            title="Alphabet revenue and P&L outlook", author="Qin (Allan) Dai")
    width = letter[0] - 1.2 * inch
    story = [Paragraph(f"Alphabet revenue and P&amp;L outlook: {qs[0]} to {qs[-1]}", h1),
             Paragraph(rl(f"Finance update, data through {last} (10-Q filed {filed}). {DISCLAIMER}"), sub),
             Paragraph(rl(sections["headline"]), base), Spacer(1, 4),
             Image(str(FIG_DIR / "forecast_total.png"), width=width * 0.82, height=width * 0.82 * 4.6 / 9)]

    def bullets(items, kind):
        return ListFlowable([ListItem(Paragraph(rl(t), base), leftIndent=10) for t in items],
                            bulletType=kind, start="1" if kind == "1" else None, leftIndent=12,
                            bulletFontSize=8.6, bulletFontName="Helvetica")

    story += [Paragraph("Top 3 drivers", h2), bullets(sections["drivers"][:3], "1"),
              Paragraph("Top 3 risks", h2), bullets(sections["risks"], "1"),
              Paragraph("Metrics to watch", h2), bullets(sections["watch"], "bullet")]
    doc.build(story)


# -------------------------------------------------------------------- README
README_START, README_END = "<!-- RESULTS:START (generated by run_pipeline.py) -->", "<!-- RESULTS:END -->"


def readme_results(result, bt, pnl_out, var, track=None, geo=None) -> str:
    sel, sn, dr = bt["selected"], bt["snaive"], bt["drift"]
    ch, meta = result["choice"], result["meta"]
    per = bt["per_line"]
    pfmt = {c: "{:.1%}" for c in ["MAPE", "WAPE", "Seasonal-naive WAPE", "80% coverage", "95% coverage"]}
    pfmt.update({c: "{:.2f}" for c in ["MASE", "Seasonal-naive MASE"]})
    pnl, ly = pnl_out["pnl"], pnl_out["ly"]
    qs = pnl_out["quarters"]
    t = var["table"]
    tfm_line = ""
    tfm_path = REPORTS_DIR / "timesfm_challenger.csv"
    if tfm_path.exists() and ((pd.read_csv(tfm_path)[["model", "method"]] == [ch["model"], ch["method"]]).all(axis=1).any()):
        tf = pd.read_csv(tfm_path)
        g = tf.groupby(["model", "method"])["mase"].mean()
        tot = tf[tf.line == "total_revenue_ex_hedging"].set_index(["model", "method"])["wape"]
        parts = []
        for name in [m for m in ["TimesFM-2.5", "TimesFM-3.0"] if m in g.index.get_level_values(0)]:
            best = g.loc[name].idxmin()
            parts.append(f"{name} ({best}): mean MASE {g.loc[(name, best)]:.2f}, total WAPE {tot.loc[(name, best)]:.1%}")
        tfm_line = (f"\n**Challengers: Google's TimesFM, zero-shot.** " + "; ".join(parts) +
                    f". Selected model: {g.loc[(ch['model'], ch['method'])]:.2f} / {tot.loc[(ch['model'], ch['method'])]:.1%}. "
                    f"[Details](reports/timesfm_challenger.md).\n")
    track_md = ""
    if track is not None:
        ts = track["summary"].set_index("config")
        rows = "\n".join(f"| {c} | {r.mean_abs_revenue_var_pct:.2f}% | {r.revenue_bias_pct:+.2f}% | {int(r.quarters_within_1pct)} of 8 | "
                         f"{r.mean_abs_oi_var_pct:.2f}% |" for c, r in ts.iterrows())
        track_md = f"""
### Track record: last 8 quarters, one quarter ahead

Each quarter was forecast with data through the previous quarter only, then compared with what Alphabet reported.

| Configuration | Mean abs. revenue variance | Bias (+ = actual above forecast) | Within ±1% | Mean abs. operating-income variance |
|---|---:|---:|---:|---:|
{rows}

![Track record](reports/figures/track_record.png)

How the configuration and cost plan were changed after v0.1, under rules committed before the tests ran: [`reports/experiments.md`](reports/experiments.md).
"""
    return f"""{README_START}
### Backtest ({len(meta['backtest_cutoffs'])} rolling origins, {meta['backtest_cutoffs'][0]}-{meta['backtest_cutoffs'][-1]}, horizons 1-4 quarters)

Selected by rules fixed in advance ([`docs/experiments.md`](docs/experiments.md)): **{ch['model']} + {ch['method']}**, {ch['intervals']} prediction intervals.

| | Selected | Seasonal naive | Drift |
|---|---:|---:|---:|
| Total revenue excl. hedging: WAPE | **{pct(sel.total_wape)}** | {pct(sn.total_wape)} | {pct(dr.total_wape)} |
| Total revenue excl. hedging: MASE | **{sel.total_mase:.2f}** | {sn.total_mase:.2f} | {dr.total_mase:.2f} |
| Mean MASE across 8 series | **{sel.mean_mase:.2f}** | {sn.mean_mase:.2f} | {dr.mean_mase:.2f} |
| 80% interval coverage | {pct(sel.coverage_80)} | {pct(sn.coverage_80)} | {pct(dr.coverage_80)} |
| 95% interval coverage | {pct(sel.coverage_95)} | {pct(sn.coverage_95)} | {pct(dr.coverage_95)} |

<details><summary>By series (selected model)</summary>

{md_table(per, pfmt, index=False)}

</details>
{tfm_line}
### Forecast

![Revenue forecast](reports/figures/forecast_total.png)

Next 4 quarters ({qs[0]}-{qs[-1]}): revenue **{bn(pnl['total_revenue'].sum())}** ({pct(pnl['total_revenue'].sum() / ly['total_revenue'].sum() - 1)} vs the prior 4 quarters),
operating income **{bn(pnl['operating_income'].sum())}**, operating margin **{pct(pnl_out['margin_next'])}** (prior 4 quarters: {pct(pnl_out['margin_prev'])}).
Full P&L: [`reports/pnl_forecast.md`](reports/pnl_forecast.md). Per-line forecasts: [`forecast_lines.png`](reports/figures/forecast_lines.png).

### Variance: {var['quarter']} forecast vs actual (held out of model selection)

Revenue {sm(t.loc['total_revenue', 'variance'])} ({t.loc['total_revenue', 'variance_pct']:+.1f}%), operating income {sm(t.loc['operating_income', 'variance'])} ({t.loc['operating_income', 'variance_pct']:+.1f}%).

![Revenue variance bridge](reports/figures/variance_revenue_waterfall.png)

![Operating income variance bridge](reports/figures/variance_oi_waterfall.png)

{track_md}
### Executive summary

One page for leadership: [`reports/exec_summary.md`](reports/exec_summary.md) · [PDF](reports/exec_summary.pdf). Scenarios and margin sensitivity: [`reports/scenarios.md`](reports/scenarios.md). Geography and FX: [`reports/geography_fx.md`](reports/geography_fx.md).
{README_END}"""


def update_readme(block: str) -> None:
    path = REPORTS_DIR.parent / "README.md"
    if not path.exists():
        return
    text = path.read_text()
    if README_START not in text:
        return
    head, rest = text.split(README_START, 1)
    tail = rest.split(README_END, 1)[1]
    path.write_text(head + block + tail)


# -------------------------------------------------------------- experiments
def experiments_report(result: dict, e2: dict, track: dict) -> str:
    ch, log = result["choice"], result["choice"]["decision_log"]
    ov = result["eval"]["overall"]
    coh = ov[ov["method"].isin(["BottomUp", "TopDown", "MinT"])]
    pts = coh[coh["intervals"] == "model"].head(10)[["model", "method", "mean_mase", "total_wape", "mean_msis",
                                                     "coverage_80", "coverage_95"]]
    kept = ov[(ov["model"] == ch["model"]) & (ov["method"] == ch["method"])][
        ["intervals", "mean_msis", "coverage_80", "coverage_95"]]
    inc = ov[(ov["model"] == log["incumbent_model"]) & (ov["method"] == log["incumbent_method"])][
        ["intervals", "mean_msis", "coverage_80", "coverage_95"]]
    improve = 1 - log["best_mean_mase"] / log["incumbent_mean_mase"]
    replaced = (ch["model"], ch["method"]) != (log["incumbent_model"], log["incumbent_method"])
    f3 = {"mean_mase": "{:.3f}", "total_wape": "{:.1%}", "mean_msis": "{:.2f}", "coverage_80": "{:.1%}",
          "coverage_95": "{:.1%}"}

    t2 = e2["table"].copy()
    t2.to_csv(REPORTS_DIR / "experiment_e2_cost_of_revenues.csv", index=False)
    t2v = t2[["quarter", "actual_pct", "incumbent_pct", "driver_pct", "auto_trend_pct", "s", "k"]].set_index("quarter")
    mae, bias = e2["mae_pp"], e2["bias_pp"]

    tr = track["table"]
    tr.to_csv(REPORTS_DIR / "track_record.csv", index=False)
    summ = track["summary"].set_index("config")
    prod = tr[tr["config"] == "production"].set_index("quarter")[
        ["model", "revenue_forecast", "revenue_actual", "revenue_variance", "revenue_variance_pct", "oi_variance_pct",
         "var_Search & other", "var_Google Cloud", "var_All other lines"]]
    picks = track["realtime_picks"].set_index("quarter")
    signs = track["line_signs"]
    charts.track_record_chart(tr[tr["config"] == "production"].reset_index(drop=True), list(signs),
                              FIG_DIR / "track_record.png",
                              "Revenue forecast vs actual, one quarter ahead, last 8 quarters",
                              f"Actual minus forecast by line group ({ch['model']} + {ch['method']}); dot = total, label = total % variance")

    text = f"""# Experiment results

Pre-registered rules: [`docs/experiments.md`](../docs/experiments.md), committed before any of these results existed.

## E1. Point model and intervals

**Point forecast.** The incumbent ({log['incumbent_model']} + {log['incumbent_method']}) has mean MASE {log['incumbent_mean_mase']:.3f}.
The best coherent challenger ({log['best_model']} + {log['best_method']}) has {log['best_mean_mase']:.3f}, which is
{improve:.1%} lower (the threshold is {log['materiality']:.0%}). **Decision: {'replace the incumbent' if replaced else 'keep the incumbent'}
→ {ch['model']} + {ch['method']}.**

**Intervals.** For {ch['model']} + {ch['method']}, mean MSIS is {log['msis_model']:.2f} with model intervals and
{log['msis_conformal']:.2f} with conformal intervals. **Decision: {ch['intervals']} intervals.**

Top 10 coherent configurations by mean MASE (model intervals):

{md_table(pts, f3, index=False)}

Interval kinds for the selected configuration:

{md_table(kept, f3, index=False)}

Same comparison for the previous production configuration:

{md_table(inc, f3, index=False)}

Reading the result:
- **Better calibrated, but now conservative.** Log-scale modeling widened the intervals where growth compounds, so coverage rose toward or above nominal. Several stable lines now reach 100% coverage, meaning their intervals are wider than needed. Cloud is still under-covered, though much less than before.
- **Conformal lost.** With 2 calibration windows, split-conformal intervals rest on very few errors per horizon, so they came out too narrow.

## E2. Cost of revenues: capex → depreciation driver

One-quarter-ahead cost-of-revenues ratio (% of revenue), actual revenue as the denominator:

{md_table(t2v, {'s': '{:+.2f}', 'k': '{:.4f}'}, default='{:.2f}')}

| Method | Mean absolute error (pp) | Mean error (pp, + = overstated) |
|---|---:|---:|
| Incumbent: same quarter last year + 0.0pp | {mae['incumbent']:.2f} | {bias['incumbent']:+.2f} |
| Challenger: depreciation driver | {mae['driver']:.2f} | {bias['driver']:+.2f} |
| Reference: same quarter last year + `auto` trend | {mae['auto_trend']:.2f} | {bias['auto_trend']:+.2f} |

**Pre-registered rule:** adopt the driver if its mean absolute error is lower. That condition is
**{'met' if e2['driver_wins'] else 'not met'}**.

**Deviation from the rule: the driver was not adopted.**
- The pass-through coefficient s is negative once it can be estimated (from 2025Q1): {t2['s'].iloc[1:].min():+.2f} to {t2['s'].iloc[1:].max():+.2f}. Read literally, a rising depreciation share would *lower* the cost-of-revenues ratio, which is not economically plausible.
- What the regression actually captures is the downward trend in the ratio, which happened while depreciation intensity rose. So the "driver" is a disguised trend model, not a depreciation model.
- Shipping it would put a wrong-signed relationship into the plan.

**What changed instead:**
- The experiment also showed that the v0.1 judgment override (hold the ratio flat) overstated cost of revenues by {bias['incumbent']:+.2f}pp on average.
- `assumptions.yaml` now uses the default rule for cost of revenues (same quarter last year + `auto` trend), the same rule R&D and S&M already use. In this comparison it also had the lowest error ({mae['auto_trend']:.2f}pp). That is disclosed here because it was seen before the switch.
- The capex → depreciation link is sensible (k > 0) and is kept as a memo projection in [`pnl_forecast.md`](pnl_forecast.md) and as a risk in the executive summary.

## E3. Forecast track record (last 8 quarters, one quarter ahead)

![Track record](figures/track_record.png)

| Configuration | Mean abs. revenue variance | Revenue bias (+ = beat) | Worst quarter | Quarters within ±1% | Mean abs. operating-income variance | OI bias |
|---|---:|---:|---:|---:|---:|---:|
""" + "\n".join(
        f"| {c} | {r.mean_abs_revenue_var_pct:.2f}% | {r.revenue_bias_pct:+.2f}% | {r.max_abs_revenue_var_pct:.2f}% | "
        f"{int(r.quarters_within_1pct)} of 8 | {r.mean_abs_oi_var_pct:.2f}% | {r.oi_bias_pct:+.2f}% |"
        for c, r in summ.iterrows()) + f"""

Production configuration by quarter (USD millions; variance = actual − forecast):

{md_table(prod, {'revenue_variance_pct': '{:+.2f}%', 'oi_variance_pct': '{:+.2f}%', 'revenue_variance': '{:+,.0f}',
                 'var_Search & other': '{:+,.0f}', 'var_Google Cloud': '{:+,.0f}', 'var_All other lines': '{:+,.0f}'},
          default='{:,.0f}')}

Direction of misses (production): """ + "; ".join(
        f"{g}: actual above forecast in {v['beat']} of 8 quarters, below in {v['miss']}" for g, v in signs.items()) + f""".

Real-time selection picked, quarter by quarter (only backtest targets before that quarter):
{", ".join(f"{q}: {r.model} + {r.method}" for q, r in picks.iterrows())}.

Caveats:
- The production configuration was selected with backtest targets through {str(pd.Period(result['meta']['holdout_quarter'], freq='Q') - 1)}, so its track record is not fully out of sample.
- Real-time selection is out of sample at every quarter.
- Operating-income variance also reflects the cost assumptions as they would have been resolved at each quarter.
"""
    (REPORTS_DIR / "experiments.md").write_text(text)
    return text


# ---------------------------------------------------------------- geography
def geography_report(con, pnl_out: dict) -> dict:
    from . import sql_layer

    geo = sql_layer.query(con, "SELECT * FROM revenue_geography ORDER BY ALL")
    fx = sql_layer.query(con, "SELECT * FROM fx_exposure ORDER BY ALL")
    last = geo["fiscal_quarter"].max()
    recent = sorted(geo["fiscal_quarter"].unique())[-8:]
    piv = geo[geo["fiscal_quarter"].isin(recent)].pivot(index="fiscal_quarter", columns="region", values="yoy_growth")
    share = geo[geo["fiscal_quarter"] == last].set_index("region")[["revenue", "share", "yoy_growth"]]
    fx_ttm = fx.tail(4)
    non_us_share_ttm = fx_ttm["non_us_revenue"].sum() / (fx_ttm["non_us_revenue"] / fx_ttm["non_us_share"]).sum()
    first = fx.iloc[0]
    next_rev = (pnl_out["pnl"]["total_revenue"] - pnl_out["pnl"]["hedging_gains_losses"]).sum()
    fx5 = next_rev * non_us_share_ttm * 0.05
    hedge = fx.tail(8)
    ser = {r: geo[(geo["region"] == r) & (geo["fiscal_quarter"] >= "2020Q1")].set_index("fiscal_quarter")["yoy_growth"]
           for r in ["United States", "EMEA", "APAC", "Other Americas"]}
    charts.multi_line_chart(ser, FIG_DIR / "geography_yoy.png", "Revenue growth by region, year over year",
                            "Quarterly revenue excl. hedging by customer location; 2020Q1 onward")
    sfmt = {"revenue": "{:,.0f}", "share": "{:.1%}", "yoy_growth": "{:+.1%}"}
    text = f"""# Geography and FX

Revenue by customer location (`sql/07_revenue_geography.sql`) and an FX lens (`sql/08_fx_exposure.sql`).
From 2019 the regions sum to revenue excluding hedging gains (losses). The 2017–2018 regional figures
include hedging, so comparisons across 2019 have a small break.

## {last}

{md_table(share, sfmt)}

## YoY growth by region, last 8 quarters

{md_table(piv, default='{:+.1%}')}

![Regional growth](figures/geography_yoy.png)

## FX exposure

- **Non-US share:** {pct(non_us_share_ttm)} of revenue excluding hedging over the last 4 quarters, vs {pct(first.non_us_share)} in {first.fiscal_quarter}.
- **Hedging results:** gains (losses) ranged from {sm(hedge['hedging_gains_losses'].min())} to {sm(hedge['hedging_gains_losses'].max())} per quarter over the last 8 quarters, i.e. {hedge['hedging_pct_of_non_us'].min():+.2%} to {hedge['hedging_pct_of_non_us'].max():+.2%} of non-US revenue.
- **Translation sensitivity (mechanical):** if the US dollar were 5% stronger against every currency for the next 4 quarters, non-US revenue would translate about **{bn(fx5)} lower** (next-4-quarter revenue excl. hedging × trailing non-US share × 5%), before hedging gains. Recent hedging results are small next to that, so most of a broad USD move would reach reported revenue.
- **Not available:** Alphabet's constant-currency growth figures are in the MD&A text and are not XBRL-tagged, so they are not used here.
"""
    (REPORTS_DIR / "geography_fx.md").write_text(text)
    return {"non_us_share_ttm": non_us_share_ttm, "fx5": fx5, "last": last, "share": share}


# ------------------------------------------------------------- productivity
def productivity_report(con) -> dict:
    from . import sql_layer

    p = sql_layer.query(con, "SELECT * FROM productivity ORDER BY fiscal_quarter")
    last8 = p.tail(8).set_index("fiscal_quarter")[["employees", "employees_yoy", "revenue_ttm_per_employee_k",
                                                    "operating_income_ttm_per_employee_k", "opex_per_employee_k_quarter"]]
    last = p.iloc[-1]
    yr = p[p["fiscal_quarter"] == str(pd.Period(last.fiscal_quarter, freq="Q") - 4)].iloc[0]
    pre = p[p["fiscal_quarter"] <= "2023Q1"]
    peak = pre.loc[pre["employees"].idxmax()]
    post = p[p["fiscal_quarter"] > peak.fiscal_quarter]
    trough = post.loc[post["employees"].idxmin()]
    text = f"""# Headcount and productivity

Quarter-end employees come from the "Number of employees" row in each earnings release (8-K exhibit 99.1);
headcount is not XBRL-tagged. Every quarter appears in two releases (current and year-ago column) and the
two values agree in every case. SQL: `sql/09_productivity.sql`. Per-employee figures are USD thousands.

{md_table(last8, {'employees': '{:,.0f}', 'employees_yoy': '{:+.1%}'}, default='{:,.0f}')}

- {last.fiscal_quarter}: {last.employees:,.0f} employees ({last.employees_yoy:+.1%} YoY); trailing-12-month revenue per employee
  ${last.revenue_ttm_per_employee_k / 1000:,.2f}M vs ${yr.revenue_ttm_per_employee_k / 1000:,.2f}M a year earlier.
- Headcount fell from its {peak.fiscal_quarter} peak of {peak.employees:,.0f} to {trough.employees:,.0f} in {trough.fiscal_quarter}
  after the 2023 layoffs, then grew again to a new high.
"""
    (REPORTS_DIR / "headcount.md").write_text(text)
    return {"employees": float(last.employees), "yoy": float(last.employees_yoy),
            "rev_per_emp_m": float(last.revenue_ttm_per_employee_k) / 1000, "quarter": last.fiscal_quarter}
