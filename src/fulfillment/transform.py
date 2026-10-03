"""Programmatic dbt invocation + persistence of run results for observability."""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from pathlib import Path

import duckdb

from fulfillment import DBT_DIR, WAREHOUSE_PATH

log = logging.getLogger("fulfillment.transform")

RESULTS_DDL = """
CREATE SCHEMA IF NOT EXISTS ops;
CREATE TABLE IF NOT EXISTS ops.dbt_run_results (
    invocation_id   VARCHAR,
    command         VARCHAR,
    generated_at    TIMESTAMP,
    unique_id       VARCHAR,
    resource_type   VARCHAR,
    status          VARCHAR,
    execution_s     DOUBLE,
    rows_affected   BIGINT,
    failures        BIGINT,
    message         VARCHAR
);
"""


@contextmanager
def _warehouse_env(warehouse: Path):
    previous = os.environ.get("FULFILLMENT_WAREHOUSE")
    os.environ["FULFILLMENT_WAREHOUSE"] = str(warehouse.resolve())
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("FULFILLMENT_WAREHOUSE", None)
        else:
            os.environ["FULFILLMENT_WAREHOUSE"] = previous


def run_dbt(args: list[str], warehouse: Path = WAREHOUSE_PATH, project_dir: Path = DBT_DIR) -> bool:
    """Run a dbt command in-process. Returns True on success and records run_results."""
    from dbt.cli.main import dbtRunner

    full = [*args, "--project-dir", str(project_dir), "--profiles-dir", str(project_dir)]
    with _warehouse_env(warehouse):
        result = dbtRunner().invoke(full)
    persist_run_results(project_dir / "target" / "run_results.json", warehouse)
    if not result.success:
        log.error("dbt %s failed: %s", " ".join(args), result.exception)
    return bool(result.success)


def persist_run_results(path: Path, warehouse: Path) -> int:
    if not path.exists():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    meta = data.get("metadata", {})
    args = data.get("args", {})
    rows = []
    for r in data.get("results", []):
        rows.append(
            [
                meta.get("invocation_id"),
                args.get("which"),
                meta.get("generated_at", "").replace("Z", ""),
                r.get("unique_id"),
                r.get("unique_id", "").split(".")[0],
                r.get("status"),
                r.get("execution_time"),
                (r.get("adapter_response") or {}).get("rows_affected"),
                r.get("failures"),
                (r.get("message") or "")[:500],
            ]
        )
    if not rows:
        return 0
    with duckdb.connect(str(warehouse)) as con:
        con.execute(RESULTS_DDL)
        con.executemany(
            "INSERT INTO ops.dbt_run_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
        )
    return len(rows)
