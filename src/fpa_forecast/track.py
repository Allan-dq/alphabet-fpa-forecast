"""E3: quarter-by-quarter forecast track record (docs/experiments.md).

For each quarter Q, the P&L for Q is forecast with data through Q-1 only (revenue h = 1, costs from
assumptions.yaml resolved as of Q-1) and compared with actuals. Three revenue configurations:

- production: the configuration selected for this release (its selection used backtest targets
  through the quarter before the holdout, so it is not fully out of sample);
- real-time selection: at each Q, the coherent combination with the lowest mean MASE on backtest
  targets strictly before Q (no incumbent rule);
- seasonal naive: the reference.
"""
from __future__ import annotations

import pandas as pd

from . import fpa
from .forecasting import evaluate, select

SNAIVE = {"model": "SeasonalNaive", "method": "base", "intervals": "model"}
GROUPS = {"Search & other": ["search_other"], "Google Cloud": ["google_cloud"],
          "All other lines": ["youtube_ads", "google_network", "subscriptions_platforms_devices",
                              "other_bets_revenue", "hedging_gains_losses"]}


def quarters_before(holdout: str, n: int = 8) -> list[str]:
    end = pd.Period(holdout, freq="Q")
    return [str(end - i) for i in range(n - 1, -1, -1)]


def track_record(wide: pd.DataFrame, result: dict, assumptions: dict, quarters: list[str]) -> dict:
    bt, hold = result["backtest"], result["holdout"]
    one_step = pd.concat([bt[bt["horizon"] == 1].drop(columns=["actual", "mase_scale"], errors="ignore"), hold],
                         ignore_index=True)
    rows, picks = [], []
    for q in quarters:
        cut = str(pd.Period(q, freq="Q") - 1)
        fc_q = one_step[one_step["cutoff"] == cut]
        rt = select(evaluate(bt[bt["fiscal_quarter"] < q])["overall"], incumbent=None)
        picks.append({"quarter": q, "model": rt["model"], "method": rt["method"]})
        for name, ch in [("production", result["choice"]), ("real-time selection", rt), ("seasonal naive", SNAIVE)]:
            v = fpa.variance(wide, fc_q, ch, assumptions, q)
            t = v["table"]
            row = {"quarter": q, "config": name, "model": f"{ch['model']} + {ch['method']}",
                   "revenue_forecast": t.loc["total_revenue", "forecast"], "revenue_actual": t.loc["total_revenue", "actual"],
                   "revenue_variance": t.loc["total_revenue", "variance"],
                   "revenue_variance_pct": t.loc["total_revenue", "variance_pct"],
                   "oi_forecast": t.loc["operating_income", "forecast"], "oi_actual": t.loc["operating_income", "actual"],
                   "oi_variance": t.loc["operating_income", "variance"],
                   "oi_variance_pct": t.loc["operating_income", "variance_pct"],
                   "margin_variance_pp": t.loc["operating_margin_pct", "variance"]}
            for g, lines in GROUPS.items():
                row[f"var_{g}"] = t.loc[lines, "variance"].sum()
            rows.append(row)
    df = pd.DataFrame(rows)
    summ = (df.groupby("config", sort=False)
            .agg(mean_abs_revenue_var_pct=("revenue_variance_pct", lambda s: s.abs().mean()),
                 revenue_bias_pct=("revenue_variance_pct", "mean"),
                 max_abs_revenue_var_pct=("revenue_variance_pct", lambda s: s.abs().max()),
                 quarters_within_1pct=("revenue_variance_pct", lambda s: int((s.abs() <= 1).sum())),
                 mean_abs_oi_var_pct=("oi_variance_pct", lambda s: s.abs().mean()),
                 oi_bias_pct=("oi_variance_pct", "mean"))
            .reset_index())
    prod = df[df["config"] == "production"]
    signs = {g: {"beat": int((prod[f"var_{g}"] > 0).sum()), "miss": int((prod[f"var_{g}"] < 0).sum())}
             for g in GROUPS}
    return {"table": df, "summary": summ, "realtime_picks": pd.DataFrame(picks), "line_signs": signs}
