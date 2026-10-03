"""End-to-end: landing -> raw -> dbt build, then prove incremental == full refresh.

Slower than the unit tests (two dbt builds); marked so it can be skipped with -m "not e2e".
dbt-duckdb keeps its connection open in-process, so tests open the warehouse with the
same (read-write) configuration instead of read_only.
"""

from datetime import date

import duckdb
import pandas as pd
import pytest

from fulfillment.generator.writer import write_landing
from fulfillment.loader import load_incremental
from fulfillment.transform import run_dbt
from tests.conftest import SMALL

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def warehouse(small_sim, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e")
    landing, wh = tmp / "landing", tmp / "warehouse.duckdb"

    # day-by-day style: first release, full build ...
    write_landing(small_sim, landing, SMALL.start, until=date(2024, 2, 29))
    load_incremental(landing, wh)
    assert run_dbt(["seed"], wh)
    assert run_dbt(["build"], wh), "initial dbt build (models + tests + unit tests) failed"

    # ... then the remaining month arrives and is processed incrementally
    write_landing(small_sim, landing, SMALL.start)
    load_incremental(landing, wh)
    assert run_dbt(["build"], wh), "incremental dbt build failed"
    return wh


@pytest.fixture(scope="module")
def landing(warehouse):
    return warehouse.parent / "landing"


def test_all_source_orders_reach_the_fact(warehouse, small_sim):
    with duckdb.connect(str(warehouse)) as con:
        n = con.execute("SELECT count(*) FROM core.fct_orders").fetchone()[0]
    assert n == small_sim.orders.order_id.nunique()


def test_incremental_fact_equals_full_refresh(warehouse, landing, tmp_path):
    # Build a second warehouse from the same landing files in one go (full refresh).
    rebuilt = tmp_path / "rebuilt.duckdb"
    load_incremental(landing, rebuilt)
    assert run_dbt(["seed"], rebuilt)
    assert run_dbt(["run", "--select", "+fct_orders", "--full-refresh"], rebuilt)

    def fact(path):
        with duckdb.connect(str(path)) as con:
            return con.execute(
                "SELECT * EXCLUDE (source_last_loaded_at) FROM core.fct_orders ORDER BY order_id"
            ).df()

    pd.testing.assert_frame_equal(fact(warehouse), fact(rebuilt))


def test_dbt_results_are_persisted(warehouse):
    with duckdb.connect(str(warehouse)) as con:
        statuses = dict(
            con.execute(
                """
                SELECT resource_type, count(*) FROM ops.dbt_run_results
                WHERE command = 'build' GROUP BY 1
                """
            ).fetchall()
        )
    assert statuses.get("unit_test", 0) >= 2
    assert statuses.get("test", 0) > 50


def test_point_in_time_attribution(warehouse):
    """Orders placed before a customer moved keep the old state."""
    with duckdb.connect(str(warehouse)) as con:
        wrong = con.execute(
            """
            SELECT count(*)
            FROM core.fct_orders f
            JOIN core.dim_customers c USING (customer_sk)
            WHERE NOT (f.purchase_at >= c.valid_from AND f.purchase_at < c.valid_to)
               OR f.customer_state IS DISTINCT FROM c.state
            """
        ).fetchone()[0]
    assert wrong == 0


def test_dagster_definitions_load(warehouse):
    pytest.importorskip("dagster_dbt")
    from fulfillment.orchestration.definitions import defs

    keys = {k.to_user_string() for k in defs.resolve_asset_graph().get_all_asset_keys()}
    assert {"landing_extracts", "raw/orders", "core/fct_orders", "kpi/mart_state_scorecard"} <= keys
    assert defs.resolve_job_def("refresh_all") is not None
    assert len(defs.resolve_asset_graph().asset_check_keys) > 50
