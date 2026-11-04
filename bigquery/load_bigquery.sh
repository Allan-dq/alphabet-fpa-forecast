#!/usr/bin/env bash
# Load the reporting tables into BigQuery and create the same views as the DuckDB layer.
#   bash bigquery/load_bigquery.sh <gcp-project-id> [dataset]
# Needs: `python run_pipeline.py` already run, and `gcloud auth login` done.
set -euo pipefail
PROJECT="$1"; DATASET="${2:-alphabet_fpa}"
BQ="${BQ:-bq}"
cd "$(dirname "$0")/.."

"$BQ" --project_id="$PROJECT" show --dataset "$PROJECT:$DATASET" >/dev/null 2>&1 \
  || "$BQ" --project_id="$PROJECT" mk --dataset --location=US "$PROJECT:$DATASET"

load() {  # table csv schema
  "$BQ" --project_id="$PROJECT" load --replace --source_format=CSV --skip_leading_rows=1 \
    "$DATASET.$1" "$2" "$3"
}
load fact_quarterly data/processed/alphabet_quarterly_long.csv \
  fiscal_quarter:STRING,period_start:DATE,period_end:DATE,line:STRING,value_m:FLOAT,derivation:STRING,restated:BOOL,first_value_m:FLOAT,n_vintages:INTEGER,source_accessions:STRING,first_accessions:STRING,source_urls:STRING
load dim_line data/reference/dim_line.csv line:STRING,line_name:STRING,category:STRING,parent:STRING,sort_order:INTEGER
load forecasts data/processed/forecasts.csv \
  run_type:STRING,model:STRING,cutoff:STRING,fiscal_quarter:STRING,horizon:INTEGER,line:STRING,forecast:FLOAT,lo_80:FLOAT,hi_80:FLOAT,lo_95:FLOAT,hi_95:FLOAT

# Views must reference fully qualified tables in BigQuery; qualify names after FROM/JOIN/VIEW.
NAMES='fact_quarterly|dim_line|forecasts|pnl_quarterly|revenue_mix|opex_ratios|segment_margin|ttm_metrics|forecast_vs_actual|revenue_geography|fx_exposure|productivity'
for f in sql/0*.sql; do
  perl -pe "s/\b(FROM|JOIN|VIEW)\s+($NAMES)\b/\1 \\\`$PROJECT.$DATASET.\2\\\`/g" "$f" \
    | "$BQ" --project_id="$PROJECT" query --use_legacy_sql=false --quiet >/dev/null
  echo "created view from $f"
done
"$BQ" --project_id="$PROJECT" query --use_legacy_sql=false --format=pretty \
  "SELECT fiscal_quarter, total_revenue, operating_income, ROUND(operating_margin, 4) AS operating_margin
   FROM \`$PROJECT.$DATASET.pnl_quarterly\` ORDER BY fiscal_quarter DESC LIMIT 4"

# Dashboard views (BigQuery-specific helpers for Looker Studio)
LABEL=$(python3 -c "import json;d=json.load(open('reports/selected_model.json'));print(d['model']+'/'+d['method']+('/conformal' if d.get('intervals')=='conformal' else ''))")
perl -pe "s/PROJECT\.DATASET/$PROJECT.$DATASET/g; s#MODEL_LABEL#$LABEL#g" bigquery/dashboard_views.sql \
  | "$BQ" --project_id="$PROJECT" query --use_legacy_sql=false --quiet >/dev/null
echo "created dashboard views (dash_*) for $LABEL"
