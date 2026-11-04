"""Write markdown/CSV reports, charts and the one-page executive summary."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import charts, fpa
from .forecasting import ID_TO_LINE, q_to_ds  # noqa: F401
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

    sel = overall[(overall.model == choice["model"]) & (overall.method == choice["method"])].iloc[0]
    snaive = overall[(overall.model == "SeasonalNaive") & (overall.method == "base")].iloc[0]
    drift = overall[(overall.model == "RWD") & (overall.method == "base")].iloc[0]
    pl = ev["per_line"]
    sel_lines = pl[(pl.model == choice["model"]) & (pl.method == choice["method"])].set_index("line")
    sn_lines = pl[(pl.model == "SeasonalNaive") & (pl.method == "base")].set_index("line")

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
    top = top[["rank", "model", "method", "mean_mase", "mean_wape", "total_wape", "total_mase", "coverage_80", "coverage_95"]]
    tfmt = {"mean_mase": "{:.3f}", "total_mase": "{:.3f}", "mean_wape": "{:.1%}", "total_wape": "{:.1%}",
            "coverage_80": "{:.1%}", "coverage_95": "{:.1%}", "rank": "{:d}"}
    cut = meta["backtest_cutoffs"]
    n_points = int(sel_lines["n"].iloc[0])
    text = f"""# Backtest results

Rolling-origin backtest, expanding window, one-quarter steps. {len(cut)} forecast origins ({cut[0]} to {cut[-1]}),
horizons 1-4 quarters, targets up to {str(pd.Period(meta['holdout_quarter'], freq='Q') - 1)}. The latest quarter
({meta['holdout_quarter']}) is held out of the backtest and used only for the variance analysis. {n_points} scored
forecasts per series. Training data start in {meta['first_quarter']}.

**Selection rule (fixed before running):** {choice['rule']}.
**Selected:** `{choice['model']}` base forecasts reconciled with `{choice['method']}`.

## Headline

| | Selected ({choice['model']} + {choice['method']}) | Seasonal naive | Random walk with drift |
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
    ratios = fpa.plan_ratios(wide, resolved, last, qs)
    rev = fpa.revenue_plan(result["live"], result["choice"], qs, assumptions["revenue"]["hedging_gains_losses_m"])
    pnl = fpa.build_pnl(rev, ratios)
    ly = fpa.actual_pnl(wide, ly_qs)
    table = fpa.pnl_table(pnl, ly)
    pnl.to_csv(REPORTS_DIR / "pnl_forecast.csv")

    res_rows = pd.DataFrame([{"Cost line": fpa.LINE_NAMES[r.line], "Method": r.method,
                              "Trend (pp YoY)": np.nan if r.trend_pp is None else r.trend_pp,
                              "Source": r.trend_source} for r in resolved])
    rat = ratios.copy()
    rat.columns = [fpa.LINE_NAMES[c] for c in rat.columns]
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
"""
    (REPORTS_DIR / "pnl_forecast.md").write_text(text)
    return {"pnl": pnl, "ly": ly, "ratios": ratios, "rev": rev, "resolved": resolved, "quarters": qs,
            "margin_next": margin_next, "margin_prev": margin_prev, "table": table}


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
    sel = live[(live.model == ch["model"]) & (live.method == ch["method"])]
    first = result["meta"]["first_quarter"]

    def fc_for(line):
        return sel[sel.line == line].sort_values("fiscal_quarter")

    charts.forecast_chart(w.loc[first:, "total_revenue_ex_hedging"], fc_for("total_revenue_ex_hedging"),
                          "Alphabet quarterly revenue (excl. hedging): actual and 8-quarter forecast",
                          f"{ch['model']} base forecasts, {ch['method']} reconciliation; shaded bands are 80% and 95% intervals",
                          FIG_DIR / "forecast_total.png")
    keys = ["search_other", "youtube_ads", "google_network", "subscriptions_platforms_devices", "google_cloud", "other_bets_revenue"]
    charts.small_multiples({k: w.loc[first:, k] for k in keys}, {k: fc_for(k) for k in keys},
                           {k: SERIES_NAMES[k] for k in keys}, FIG_DIR / "forecast_lines.png",
                           "Revenue lines: actual and forecast (reconciled)")


# ------------------------------------------------------------ exec summary
def exec_summary(wide, con, result, bt, pnl_out, var, sc, assumptions) -> str:
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
    cloud_end = live[(live.model == ch["model"]) & (live.method == ch["method"]) & (live.line == "google_cloud")
                     & (live.fiscal_quarter == qs[-1])].iloc[0]
    sens = sc["sensitivity"]
    cases = sc["cases"]
    one_pp_cor = rev_next * 0.01
    rv = var["table"]

    headline = (f"For the next four quarters ({qs[0]}-{qs[-1]}) we forecast revenue of **{bn(rev_next)}**, "
                f"{pct(rev_next / rev_prev - 1)} above the last four reported quarters, and operating income of "
                f"**{bn(oi_next)}** (margin **{pct(pnl_out['margin_next'])}** vs {pct(pnl_out['margin_prev'])}). "
                f"The model ({ch['model']} + {ch['method']} reconciliation) was chosen on a {len(result['meta']['backtest_cutoffs'])}-origin "
                f"backtest: total-revenue WAPE {pct(bt['selected'].total_wape)} vs {pct(bt['snaive'].total_wape)} for seasonal naive. "
                f"On the held-out quarter ({var['quarter']}) actual revenue differed from forecast by "
                f"{sm(rv.loc['total_revenue','variance'])} ({rv.loc['total_revenue','variance_pct']:+.1f}%) and operating income by "
                f"{sm(rv.loc['operating_income','variance'])} ({rv.loc['operating_income','variance_pct']:+.1f}%).")

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
        f"**Depreciation pressure on cost of revenues.** Trailing-12-month capex reached {pct(ttm.iloc[-1].capex_intensity_ttm)} of revenue "
        f"in {last} vs {pct(ttm.iloc[0].capex_intensity_ttm)} a year earlier. The plan holds the cost-of-revenues ratio flat year over year; "
        f"each +1pp would cut operating income by about {bn(one_pp_cor)} over four quarters.",
        f"**Search growth.** Search & other is {pct(mix.loc['search_other','share_of_total'])} of {last} revenue and came in "
        f"{rv.loc['search_other','variance_pct']:+.1f}% vs forecast in {var['quarter']}. The downside case (Search -2pp, Cloud -5pp) "
        f"lowers four-quarter revenue by {bn(cases.loc['base','revenue'] - cases.loc['downside','revenue'])} and margin to "
        f"{cases.loc['downside','operating_margin_pct']:.1f}%.",
    ]
    watch = [
        f"Google Cloud QoQ growth ({pct(mix.loc['google_cloud','qoq_growth'])} in {last}) and segment margin ({pct(seg.loc['Google Cloud','operating_margin'])}).",
        f"Search & other YoY growth ({pct(mix.loc['search_other','yoy_growth'])} in {last}).",
        f"Capex intensity, TTM ({pct(ttm.iloc[-1].capex_intensity_ttm)}) and cost of revenues as % of revenue.",
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

Details: [P&L](pnl_forecast.md) · [backtest](backtest_summary.md) · [variance](variance_""" + var["quarter"] + """.md) · [scenarios](scenarios.md) · [method](../docs/methodology.md)
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


def readme_results(result, bt, pnl_out, var) -> str:
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
    if tfm_path.exists():
        tf = pd.read_csv(tfm_path)
        g = tf.groupby(["model", "method"])["mase"].mean()
        tot = tf[tf.line == "total_revenue_ex_hedging"].set_index(["model", "method"])["wape"]
        best_tfm = g.loc["TimesFM-2.5"].idxmin()
        tfm_line = (f"\n**Challenger: TimesFM 2.5 (zero-shot).** Best variant `{best_tfm}`: mean MASE "
                    f"{g.loc[('TimesFM-2.5', best_tfm)]:.2f}, total WAPE {tot.loc[('TimesFM-2.5', best_tfm)]:.1%}, vs "
                    f"{g.loc[(ch['model'], ch['method'])]:.2f} / {tot.loc[(ch['model'], ch['method'])]:.1%} for the selected model. "
                    f"[Details](reports/timesfm_challenger.md).\n")
    return f"""{README_START}
### Backtest ({len(meta['backtest_cutoffs'])} rolling origins, {meta['backtest_cutoffs'][0]}-{meta['backtest_cutoffs'][-1]}, horizons 1-4 quarters)

Selected by a rule fixed in advance (lowest mean MASE across the 8 hierarchy series): **{ch['model']} + {ch['method']}**.

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

### Executive summary

One page for leadership: [`reports/exec_summary.md`](reports/exec_summary.md) · [PDF](reports/exec_summary.pdf). Scenarios and margin sensitivity: [`reports/scenarios.md`](reports/scenarios.md).
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
