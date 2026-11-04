"""Run the whole pipeline: data -> SQL layer -> forecasts/backtest -> FP&A reports.

    python run_pipeline.py                # use committed data/processed (no network)
    python run_pipeline.py --rebuild-data # re-parse cached XBRL in data/raw
    python run_pipeline.py --fetch        # download filings from SEC EDGAR first
                                          # (needs SEC_USER_AGENT="Name email")
"""
from __future__ import annotations

import argparse
import json
import time

import pandas as pd

from fpa_forecast import dataset, forecasting, fpa, report, sql_layer, track
from fpa_forecast.fpa import load_assumptions
from fpa_forecast.paths import DB_PATH, FIG_DIR, INTERIM_DIR, PROCESSED_DIR, REPORTS_DIR


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="download 10-Q/10-K XBRL from SEC EDGAR")
    ap.add_argument("--rebuild-data", action="store_true", help="rebuild the dataset from data/raw")
    args = ap.parse_args()
    t0 = time.time()
    REPORTS_DIR.mkdir(exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    if args.fetch:
        from fpa_forecast import sec_fetch
        print("[1/5] fetching filings from SEC EDGAR")
        sec_fetch.fetch_all()
    if args.fetch or args.rebuild_data:
        print("[1/5] building quarterly dataset from XBRL")
        dataset.build()
    else:
        print("[1/5] using committed dataset in data/processed")
    wide = pd.read_csv(PROCESSED_DIR / "alphabet_quarterly_wide.csv")
    last_filed = pd.read_csv(INTERIM_DIR / "xbrl_facts_mapped.csv.gz", usecols=["filed"])["filed"].max()

    assumptions = load_assumptions()
    holdout = assumptions["holdout_quarter"]
    print(f"[2/5] backtest + forecasts (holdout {holdout})")
    result = forecasting.run(wide, holdout=holdout, backtest_cutoffs=forecasting.default_cutoffs(holdout),
                             live_horizon=assumptions["chart_horizon_quarters"])
    result["meta"]["last_filed"] = last_filed
    (REPORTS_DIR / "selected_model.json").write_text(json.dumps({**result["choice"], **result["meta"]}, indent=2))

    print("[3/5] DuckDB reporting layer")
    fc_table = forecasting.forecasts_table(result)
    fc_table.to_csv(PROCESSED_DIR / "forecasts.csv", index=False)
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sql_layer.build(DB_PATH, forecasts=fc_table)
    sql_out = REPORTS_DIR / "sql"
    sql_out.mkdir(exist_ok=True)
    for view in ["pnl_quarterly", "revenue_mix", "opex_ratios", "segment_margin", "ttm_metrics", "revenue_geography",
                 "fx_exposure", "productivity"]:
        sql_layer.query(con, f"SELECT * FROM {view} ORDER BY ALL").to_csv(sql_out / f"{view}.csv", index=False)
    sql_layer.query(con, (REPORTS_DIR.parent / "sql" / "queries" / "backtest_accuracy.sql").read_text()).to_csv(
        sql_out / "backtest_accuracy.csv", index=False)

    print("[4/5] FP&A reports")
    bt = report.backtest_report(result)
    pnl_out = report.pnl_report(wide, result, assumptions)
    var = report.variance_report(wide, result, assumptions)
    sc = report.scenario_report(wide, pnl_out, assumptions)
    report.forecast_charts(wide, result)

    quarters = track.quarters_before(holdout, 8)
    e2 = fpa.cost_driver_experiment(wide, quarters)
    tr = track.track_record(wide, result, assumptions, quarters)
    report.experiments_report(result, e2, tr)
    geo = report.geography_report(con, pnl_out)
    prod = report.productivity_report(con)

    print("[5/5] executive summary")
    report.exec_summary(wide, con, result, bt, pnl_out, var, sc, assumptions, track=tr, geo=geo, hc=prod)
    report.update_readme(report.readme_results(result, bt, pnl_out, var, track=tr, geo=geo))
    con.close()
    print(f"done in {time.time() - t0:.0f}s -> reports/")


if __name__ == "__main__":
    main()
