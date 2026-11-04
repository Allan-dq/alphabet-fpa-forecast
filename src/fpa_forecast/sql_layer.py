"""DuckDB reporting layer.

Tables
  fact_quarterly  one row per (fiscal_quarter, line) from data/processed
  dim_line        line names, category and hierarchy parent
  forecasts       backtest and live forecasts (written by the forecasting step)

Views are defined in sql/*.sql in plain ANSI SQL that also runs on BigQuery
(see bigquery/README.md).
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from .paths import DATA_DIR, DB_PATH, PROCESSED_DIR, SQL_DIR

FORECAST_COLUMNS = ["run_type", "model", "cutoff", "fiscal_quarter", "horizon", "line",
                    "forecast", "lo_80", "hi_80", "lo_95", "hi_95"]


def connect(path: Path | str = DB_PATH) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(path))


def load_tables(con: duckdb.DuckDBPyConnection, forecasts: pd.DataFrame | None = None) -> None:
    fact = pd.read_csv(PROCESSED_DIR / "alphabet_quarterly_long.csv",
                       parse_dates=["period_start", "period_end"])
    fact["restated"] = fact["restated"].astype(bool)
    dim = pd.read_csv(DATA_DIR / "reference" / "dim_line.csv")
    con.register("fact_df", fact)
    con.register("dim_df", dim)
    con.execute("CREATE OR REPLACE TABLE fact_quarterly AS SELECT * FROM fact_df")
    con.execute("CREATE OR REPLACE TABLE dim_line AS SELECT * FROM dim_df")
    con.unregister("fact_df")
    con.unregister("dim_df")
    write_forecasts(con, forecasts if forecasts is not None else pd.DataFrame(columns=FORECAST_COLUMNS))


def write_forecasts(con: duckdb.DuckDBPyConnection, forecasts: pd.DataFrame) -> None:
    fc = forecasts.reindex(columns=FORECAST_COLUMNS).copy()
    for c in ["run_type", "model", "cutoff", "fiscal_quarter", "line"]:
        fc[c] = fc[c].astype("string")
    fc["horizon"] = pd.to_numeric(fc["horizon"]).astype("Int64")
    for c in ["forecast", "lo_80", "hi_80", "lo_95", "hi_95"]:
        fc[c] = pd.to_numeric(fc[c]).astype(float)
    con.register("fc_df", fc)
    con.execute("CREATE OR REPLACE TABLE forecasts AS SELECT * FROM fc_df")
    con.unregister("fc_df")


def create_views(con: duckdb.DuckDBPyConnection) -> list[str]:
    created = []
    for path in sorted(SQL_DIR.glob("*.sql")):
        con.execute(path.read_text())
        created.append(path.stem)
    return created


def build(path: Path | str = DB_PATH, forecasts: pd.DataFrame | None = None) -> duckdb.DuckDBPyConnection:
    con = connect(path)
    load_tables(con, forecasts)
    create_views(con)
    return con


def query(con: duckdb.DuckDBPyConnection, sql: str) -> pd.DataFrame:
    return con.execute(sql).df()
