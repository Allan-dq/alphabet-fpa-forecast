"""Compare every view in BigQuery with the same view in DuckDB (row counts and column sums).

    PATH="$HOME/google-cloud-sdk/bin:$PATH" python bigquery/verify_against_duckdb.py <project> [dataset]
"""
import json
import subprocess
import sys

import pandas as pd

from fpa_forecast import sql_layer

PROJECT = sys.argv[1]
DATASET = sys.argv[2] if len(sys.argv) > 2 else "alphabet_fpa"
VIEWS = ["pnl_quarterly", "revenue_mix", "opex_ratios", "segment_margin", "ttm_metrics", "forecast_vs_actual",
         "revenue_geography", "fx_exposure", "productivity"]

forecasts = pd.read_csv("data/processed/forecasts.csv")
con = sql_layer.build(":memory:", forecasts=forecasts)
rows, ok = [], True
for v in VIEWS:
    local = sql_layer.query(con, f"SELECT * FROM {v}")
    num = [c for c in local.select_dtypes("number").columns]
    sums = ", ".join(f"SUM(CAST({c} AS FLOAT64)) AS {c}" for c in num)
    q = f"SELECT COUNT(*) AS n, {sums} FROM `{PROJECT}.{DATASET}.{v}`"
    out = subprocess.run(["bq", f"--project_id={PROJECT}", "query", "--use_legacy_sql=false", "--format=json", q],
                         capture_output=True, text=True, check=True).stdout
    bq = {k: float(x) if x is not None else 0.0 for k, x in json.loads(out)[0].items()}
    worst = max((abs(bq[c] - float(local[c].sum())) / max(1.0, abs(float(local[c].sum()))) for c in num), default=0.0)
    same_n = int(bq["n"]) == len(local)
    ok &= same_n and worst < 1e-9
    rows.append((v, len(local), int(bq["n"]), len(num), worst))
    print(f"{v:20s} rows duckdb={len(local):6d} bigquery={int(bq['n']):6d}  numeric cols={len(num):2d}  max rel diff of sums={worst:.1e}")
print("ALL VIEWS MATCH" if ok else "MISMATCH")
sys.exit(0 if ok else 1)
