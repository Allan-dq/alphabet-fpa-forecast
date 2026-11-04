from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
SQL_DIR = REPO_ROOT / "sql"
REPORTS_DIR = REPO_ROOT / "reports"
FIG_DIR = REPORTS_DIR / "figures"
DB_PATH = DATA_DIR / "fpa.duckdb"
