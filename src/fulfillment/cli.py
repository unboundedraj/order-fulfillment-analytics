"""`fulfillment` command line.

fulfillment generate [--until 2025-06-30]    simulate + write landing extracts
fulfillment load                              incremental raw load
fulfillment transform [--full-refresh]        dbt seed + build (models, tests, unit tests)
fulfillment run                               generate -> load -> transform
fulfillment advance --days 7                  release N more days and process them incrementally
fulfillment status                            warehouse row counts, last loads, last dbt run
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb

from fulfillment import DATA_DIR, LANDING_DIR, WAREHOUSE_PATH
from fulfillment.generator.simulate import SimulationConfig, simulate
from fulfillment.generator.writer import write_landing
from fulfillment.loader import load_incremental
from fulfillment.transform import run_dbt

log = logging.getLogger("fulfillment")


def _config(args) -> SimulationConfig:
    kw = {}
    if getattr(args, "start", None):
        kw["start"] = date.fromisoformat(args.start)
    if getattr(args, "end", None):
        kw["end"] = date.fromisoformat(args.end)
    if getattr(args, "orders_per_day", None):
        kw["orders_per_day"] = args.orders_per_day
    if getattr(args, "seed", None) is not None:
        kw["seed"] = args.seed
    return SimulationConfig(**kw)


def _latest_landed_day(landing: Path) -> date | None:
    days = sorted(p.name[3:] for p in (landing / "orders").glob("dt=*"))
    return date.fromisoformat(days[-1]) if days else None


def cmd_generate(args) -> None:
    cfg = _config(args)
    until = date.fromisoformat(args.until) if args.until else None
    written = write_landing(simulate(cfg), Path(args.landing), cfg.start, until)
    log.info("landing files written: %s", written)


def cmd_load(args) -> None:
    report = load_incremental(Path(args.landing), Path(args.warehouse))
    print(report.to_json())


def cmd_transform(args) -> None:
    wh = Path(args.warehouse)
    ok = run_dbt(["seed"], wh) and run_dbt(
        ["build", *(["--full-refresh"] if args.full_refresh else [])], wh
    )
    if not ok:
        sys.exit(1)


def cmd_advance(args) -> None:
    """Release the next N days of extracts and process them incrementally."""
    cfg = _config(args)
    landing, wh = Path(args.landing), Path(args.warehouse)
    last = _latest_landed_day(landing) or (cfg.start - timedelta(days=1))
    until = min(last + timedelta(days=args.days), cfg.end)
    write_landing(simulate(cfg), landing, cfg.start, until)
    print(load_incremental(landing, wh).to_json())
    if not (run_dbt(["seed"], wh) and run_dbt(["build"], wh)):
        sys.exit(1)
    log.info("advanced landing to %s", until)


def cmd_run(args) -> None:
    cmd_generate(args)
    cmd_load(args)
    cmd_transform(args)


def cmd_status(args) -> None:
    with duckdb.connect(str(args.warehouse), read_only=True) as con:
        print(
            con.sql(
                """
                SELECT entity, count(*) AS files, sum(rows_loaded) AS rows, max(loaded_at) AS last_load
                FROM raw._load_manifest GROUP BY 1 ORDER BY 1
                """
            )
        )
        print(
            con.sql(
                """
                SELECT schema_name, table_name, estimated_size AS approx_rows
                FROM duckdb_tables()
                WHERE schema_name IN ('core', 'kpi')
                ORDER BY 1, 2
                """
            )
        )
        print(
            con.sql(
                """
                SELECT resource_type, status, count(*) AS n, round(sum(execution_s), 1) AS seconds
                FROM ops.dbt_run_results
                WHERE invocation_id = (
                    SELECT invocation_id FROM ops.dbt_run_results ORDER BY generated_at DESC LIMIT 1)
                GROUP BY ALL ORDER BY 1, 2
                """
            )
        )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fulfillment",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--landing", default=str(LANDING_DIR))
    p.add_argument("--warehouse", default=str(WAREHOUSE_PATH))
    sub = p.add_subparsers(dest="command", required=True)

    def sim_args(sp):
        sp.add_argument("--start", help="simulation start date (default 2024-01-01)")
        sp.add_argument("--end", help="simulation end date (default 2025-12-31)")
        sp.add_argument("--orders-per-day", type=float)
        sp.add_argument("--seed", type=int)

    g = sub.add_parser("generate", help="simulate and write landing extracts")
    sim_args(g)
    g.add_argument("--until", help="only release extracts up to this date")
    sub.add_parser("load", help="incrementally load new landing files into raw")
    t = sub.add_parser("transform", help="dbt seed + build")
    t.add_argument("--full-refresh", action="store_true")
    r = sub.add_parser("run", help="generate -> load -> transform")
    sim_args(r)
    r.add_argument("--until")
    r.add_argument("--full-refresh", action="store_true")
    a = sub.add_parser("advance", help="release N more days and process incrementally")
    sim_args(a)
    a.add_argument("--days", type=int, default=1)
    sub.add_parser("status", help="warehouse summary")
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    )
    args = build_parser().parse_args(argv)
    DATA_DIR.mkdir(exist_ok=True)
    {
        "generate": cmd_generate,
        "load": cmd_load,
        "transform": cmd_transform,
        "run": cmd_run,
        "advance": cmd_advance,
        "status": cmd_status,
    }[args.command](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
