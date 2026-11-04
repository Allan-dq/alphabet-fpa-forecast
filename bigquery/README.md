# Running the SQL layer on BigQuery

The views in [`../sql`](../sql) are written in ANSI SQL that DuckDB and BigQuery both accept: conditional aggregation, `LAG`, named `WINDOW` clauses and `NULLIF` division. The BigQuery sandbox (free, no billing account) is enough.

> Status: these steps are documentation only. No BigQuery dataset or Looker Studio dashboard has been built for this repo yet.

```bash
# 1. Create a dataset in your own project
bq mk --dataset YOUR_PROJECT:alphabet_fpa

# 2. Load the tables produced by `python run_pipeline.py`
bq load --autodetect --source_format=CSV alphabet_fpa.fact_quarterly data/processed/alphabet_quarterly_long.csv
bq load --autodetect --source_format=CSV alphabet_fpa.dim_line       data/reference/dim_line.csv
bq load --autodetect --source_format=CSV alphabet_fpa.forecasts      data/processed/forecasts.csv

# 3. Create the views; the default dataset resolves the unqualified table names
for f in sql/0*.sql; do
  bq query --use_legacy_sql=false --dataset_id=YOUR_PROJECT:alphabet_fpa < "$f"
done
```

Notes
- BigQuery needs `CREATE OR REPLACE VIEW alphabet_fpa.<name>` when no default dataset is set. The `--dataset_id` flag above avoids editing the files.
- `period_end` is loaded as `DATE` by autodetect. `LAG(...) OVER (... ORDER BY period_end)` works the same in both engines.
- A Looker Studio report or Connected Sheet can read `pnl_quarterly`, `revenue_mix` and `forecast_vs_actual` directly.
