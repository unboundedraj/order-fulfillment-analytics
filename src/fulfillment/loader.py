"""Incremental, idempotent loader: landing CSV files -> DuckDB `raw` schema.

* Each entity has an append-only raw table with lineage columns
  (`_source_file`, `_loaded_at`, `_load_id`).
* `raw._load_manifest` records every file already loaded together with its size and
  modification time, so re-running the loader only picks up new files, and a file that
  changed after loading is flagged instead of being silently double-loaded.
* Loading a file and recording it in the manifest happen in one transaction.

Deduplication and "latest version wins" logic intentionally live in dbt staging
models, not here: raw stays a faithful copy of what the source sent.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

log = logging.getLogger("fulfillment.loader")

# Explicit raw schemas - never rely on CSV type sniffing for a production feed.
SCHEMAS: dict[str, dict[str, str]] = {
    "orders": {
        "order_id": "VARCHAR",
        "customer_id": "VARCHAR",
        "hub_id": "VARCHAR",
        "courier": "VARCHAR",
        "payment_method": "VARCHAR",
        "purchase_at": "TIMESTAMP",
        "estimated_delivery_date": "DATE",
        "order_status": "VARCHAR",
        "approved_at": "TIMESTAMP",
        "shipped_at": "TIMESTAMP",
        "delivered_at": "TIMESTAMP",
        "closed_at": "TIMESTAMP",
        "updated_at": "TIMESTAMP",
    },
    "order_items": {
        "order_id": "VARCHAR",
        "order_item_seq": "INTEGER",
        "product_id": "VARCHAR",
        "seller_id": "VARCHAR",
        "quantity": "INTEGER",
        "unit_price": "DECIMAL(12,2)",
        "created_at": "TIMESTAMP",
    },
    "payments": {
        "payment_id": "VARCHAR",
        "order_id": "VARCHAR",
        "payment_type": "VARCHAR",
        "payment_method": "VARCHAR",
        "amount": "DECIMAL(12,2)",
        "created_at": "TIMESTAMP",
    },
    "customers": {
        "customer_id": "VARCHAR",
        "pincode": "VARCHAR",
        "signup_at": "TIMESTAMP",
        "updated_at": "TIMESTAMP",
        "state": "VARCHAR",
    },
}

SNAPSHOTS: dict[str, dict[str, str]] = {
    "products": {
        "product_id": "VARCHAR",
        "category": "VARCHAR",
        "list_price": "DECIMAL(12,2)",
        "weight_kg": "DOUBLE",
        "seller_id": "VARCHAR",
    },
    "sellers": {
        "seller_id": "VARCHAR",
        "seller_name": "VARCHAR",
        "hub_id": "VARCHAR",
        "hub_state": "VARCHAR",
        "onboarded_at": "TIMESTAMP",
    },
}

MANIFEST_DDL = """
CREATE SCHEMA IF NOT EXISTS raw;
CREATE TABLE IF NOT EXISTS raw._load_manifest (
    entity       VARCHAR,
    file_path    VARCHAR,
    file_bytes   BIGINT,
    file_mtime   DOUBLE,
    rows_loaded  BIGINT,
    load_id      VARCHAR,
    loaded_at    TIMESTAMP,
    PRIMARY KEY (entity, file_path)
);
"""


@dataclass
class LoadReport:
    load_id: str
    files_loaded: dict[str, int]
    rows_loaded: dict[str, int]
    files_skipped: int
    files_changed_since_load: list[str]

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2)


def _columns_sql(schema: dict[str, str]) -> str:
    return "{" + ", ".join(f"'{k}': '{v}'" for k, v in schema.items()) + "}"


def _ensure_table(con: duckdb.DuckDBPyConnection, entity: str, schema: dict[str, str]) -> None:
    cols = ", ".join(f"{k} {v}" for k, v in schema.items())
    con.execute(
        f"CREATE TABLE IF NOT EXISTS raw.{entity} ({cols}, "
        "_source_file VARCHAR, _loaded_at TIMESTAMP, _load_id VARCHAR)"
    )


def load_incremental(landing: Path, warehouse: Path) -> LoadReport:
    warehouse.parent.mkdir(parents=True, exist_ok=True)
    load_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
    files_loaded: dict[str, int] = {}
    rows_loaded: dict[str, int] = {}
    skipped = 0
    changed: list[str] = []

    with duckdb.connect(str(warehouse)) as con:
        con.execute("SET enable_progress_bar = false")
        con.execute(MANIFEST_DDL)
        manifest = {
            (e, p): (b, m)
            for e, p, b, m in con.execute(
                "SELECT entity, file_path, file_bytes, file_mtime FROM raw._load_manifest"
            ).fetchall()
        }

        for entity, schema in SCHEMAS.items():
            _ensure_table(con, entity, schema)
            new_files = []
            for f in sorted((landing / entity).glob("dt=*/*.csv")):
                rel = f.relative_to(landing).as_posix()
                stat = f.stat()
                if (entity, rel) in manifest:
                    if manifest[(entity, rel)] != (stat.st_size, stat.st_mtime):
                        changed.append(rel)
                    skipped += 1
                    continue
                new_files.append((str(f), rel, stat.st_size, stat.st_mtime))
            files_loaded[entity] = len(new_files)
            rows_loaded[entity] = 0
            if not new_files:
                continue

            # All new files of an entity are read in one multi-file scan and committed
            # atomically together with their manifest entries.
            files_df = pd.DataFrame(new_files, columns=["path", "rel", "bytes", "mtime"])
            con.register("_files", files_df)
            con.execute("BEGIN TRANSACTION")
            try:
                con.execute(
                    f"""
                    CREATE OR REPLACE TEMP TABLE _stage AS
                    SELECT * FROM read_csv(?, header = true, columns = {_columns_sql(schema)},
                                           timestampformat = '%Y-%m-%d %H:%M:%S',
                                           hive_partitioning = false, filename = true)
                    """,
                    [files_df["path"].tolist()],
                )
                rows_loaded[entity] = con.execute(
                    f"""
                    INSERT INTO raw.{entity}
                    SELECT s.* EXCLUDE (filename), f.rel, now()::TIMESTAMP, ?
                    FROM _stage s JOIN _files f ON s.filename = f.path
                    """,
                    [load_id],
                ).fetchone()[0]
                con.execute(
                    """
                    INSERT INTO raw._load_manifest
                    SELECT ?, f.rel, f.bytes, f.mtime, coalesce(c.n, 0), ?, now()::TIMESTAMP
                    FROM _files f
                    LEFT JOIN (SELECT filename, count(*) AS n FROM _stage GROUP BY 1) c
                           ON c.filename = f.path
                    """,
                    [entity, load_id],
                )
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
            finally:
                con.unregister("_files")

        # Catalog snapshots are small: full refresh each run.
        for entity, schema in SNAPSHOTS.items():
            path = landing / "catalog" / f"{entity}.csv"
            if not path.exists():
                continue
            cols = ", ".join(f"{k} {v}" for k, v in schema.items())
            con.execute(f"CREATE OR REPLACE TABLE raw.{entity} ({cols}, _loaded_at TIMESTAMP)")
            con.execute(
                f"INSERT INTO raw.{entity} SELECT *, now()::TIMESTAMP FROM read_csv(?, header = true, "
                f"columns = {_columns_sql(schema)}, timestampformat = '%Y-%m-%d %H:%M:%S')",
                [str(path)],
            )

    report = LoadReport(load_id, files_loaded, rows_loaded, skipped, changed)
    if changed:
        log.warning(
            "%d landing files changed after they were loaded: %s", len(changed), changed[:5]
        )
    log.info("load %s: files=%s rows=%s skipped=%s", load_id, files_loaded, rows_loaded, skipped)
    return report
