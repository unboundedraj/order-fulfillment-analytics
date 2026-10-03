"""Order fulfillment & delivery analytics platform."""

from pathlib import Path

__version__ = "0.1.0"

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
LANDING_DIR = DATA_DIR / "landing"
WAREHOUSE_PATH = DATA_DIR / "warehouse.duckdb"
DBT_DIR = REPO_ROOT / "dbt"
