"""Dagster code location: landing extracts -> raw tables -> every dbt model as an asset.

    dagster dev -m fulfillment.orchestration.definitions      # UI on http://localhost:3000

* `landing_extracts`  releases the next N days of source extracts (simulated OMS export)
* `raw_*` assets      incremental, manifest-tracked load into DuckDB `raw`
* dbt assets          one asset per seed/model, with dbt tests surfaced as asset checks
* `daily_refresh`     schedule: advance one day and rebuild everything downstream
* `new_extracts`      sensor: triggers a load + build when new files appear in landing
"""

import os
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

from dagster import (
    AssetExecutionContext,
    AssetKey,
    AssetSelection,
    AssetSpec,
    Config,
    DefaultScheduleStatus,
    DefaultSensorStatus,
    Definitions,
    MaterializeResult,
    MetadataValue,
    RunRequest,
    ScheduleDefinition,
    SensorEvaluationContext,
    SkipReason,
    asset,
    define_asset_job,
    multi_asset,
    sensor,
)
from dagster_dbt import DbtCliResource, DbtProject, dbt_assets

from fulfillment import DBT_DIR, LANDING_DIR, WAREHOUSE_PATH
from fulfillment.generator.simulate import SimulationConfig, simulate
from fulfillment.generator.writer import write_landing
from fulfillment.loader import SCHEMAS, SNAPSHOTS, load_incremental

os.environ.setdefault("FULFILLMENT_WAREHOUSE", str(WAREHOUSE_PATH))

dbt_project = DbtProject(project_dir=DBT_DIR, profiles_dir=DBT_DIR)
dbt_project.prepare_if_dev()

RAW_TABLES = [*SCHEMAS, *SNAPSHOTS]

# Prefer the dbt that lives next to the running interpreter (works without an activated venv).
_local_dbt = Path(sys.executable).parent / ("dbt.exe" if os.name == "nt" else "dbt")
DBT_EXECUTABLE = str(_local_dbt) if _local_dbt.exists() else (shutil.which("dbt") or "dbt")


class AdvanceConfig(Config):
    days: int = 1


def _latest_landed_day(landing: Path) -> "date | None":
    days = sorted(p.name[3:] for p in (landing / "orders").glob("dt=*"))
    return date.fromisoformat(days[-1]) if days else None


@asset(group_name="ingestion", compute_kind="python")
def landing_extracts(context: AssetExecutionContext, config: AdvanceConfig) -> MaterializeResult:
    """Release the next `days` days of OMS extracts into the landing zone."""
    cfg = SimulationConfig()
    last = _latest_landed_day(LANDING_DIR) or (cfg.start - timedelta(days=1))
    until = min(last + timedelta(days=config.days), cfg.end)
    written = write_landing(simulate(cfg), LANDING_DIR, cfg.start, until)
    context.log.info("released extracts up to %s: %s", until, written)
    return MaterializeResult(
        metadata={"released_until": str(until), "files_written": MetadataValue.json(written)}
    )


@multi_asset(
    specs=[
        AssetSpec(
            AssetKey(["raw", t]), deps=[landing_extracts], group_name="ingestion", kinds={"duckdb"}
        )
        for t in RAW_TABLES
    ],
    can_subset=False,
)
def raw_tables(context: AssetExecutionContext):
    """Incrementally load new landing files into DuckDB raw.* (manifest-tracked, idempotent)."""
    report = load_incremental(LANDING_DIR, WAREHOUSE_PATH)
    if report.files_changed_since_load:
        context.log.warning("files changed after load: %s", report.files_changed_since_load[:10])
    for t in RAW_TABLES:
        yield MaterializeResult(
            asset_key=AssetKey(["raw", t]),
            metadata={
                "load_id": report.load_id,
                "files_loaded": report.files_loaded.get(t, 0),
                "rows_loaded": report.rows_loaded.get(t, 0),
                "files_skipped_total": report.files_skipped,
            },
        )


@dbt_assets(manifest=dbt_project.manifest_path, project=dbt_project)
def fulfillment_dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    """Every dbt seed/model is an asset; dbt tests run as asset checks."""
    yield from dbt.cli(["build"], context=context).stream()


everything = define_asset_job(
    "refresh_all", selection=AssetSelection.all(), description="advance -> load -> dbt build"
)
load_and_transform = define_asset_job(
    "load_and_transform",
    selection=AssetSelection.all() - AssetSelection.assets(landing_extracts),
)

daily_refresh = ScheduleDefinition(
    job=everything,
    cron_schedule="0 6 * * *",
    execution_timezone="Asia/Kolkata",
    default_status=DefaultScheduleStatus.STOPPED,
)


@sensor(
    job=load_and_transform, minimum_interval_seconds=60, default_status=DefaultSensorStatus.STOPPED
)
def new_extracts(context: SensorEvaluationContext):
    """Kick off load + transform when a new extract day lands (e.g. dropped by an upstream team)."""
    latest = _latest_landed_day(LANDING_DIR)
    if latest is None:
        return SkipReason("landing zone is empty")
    if context.cursor == latest.isoformat():
        return SkipReason(f"no new extracts since {latest}")
    context.update_cursor(latest.isoformat())
    return RunRequest(run_key=f"extracts-{latest.isoformat()}")


defs = Definitions(
    assets=[landing_extracts, raw_tables, fulfillment_dbt_assets],
    jobs=[everything, load_and_transform],
    schedules=[daily_refresh],
    sensors=[new_extracts],
    resources={"dbt": DbtCliResource(project_dir=dbt_project, dbt_executable=DBT_EXECUTABLE)},
)
