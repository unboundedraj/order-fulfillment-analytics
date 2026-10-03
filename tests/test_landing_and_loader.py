import os
from datetime import date

import duckdb
import pandas as pd

from fulfillment import DBT_DIR
from fulfillment.generator.seeds import seed_frames
from fulfillment.generator.writer import write_landing
from fulfillment.loader import load_incremental
from tests.conftest import SMALL


def _count(wh, table):
    with duckdb.connect(str(wh), read_only=True) as con:
        return con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_writer_releases_days_incrementally(small_sim, tmp_path):
    first = write_landing(small_sim, tmp_path, SMALL.start, until=date(2024, 1, 31))
    assert first["orders"] == 31
    again = write_landing(small_sim, tmp_path, SMALL.start, until=date(2024, 1, 31))
    assert again["orders"] == 0  # existing days untouched
    more = write_landing(small_sim, tmp_path, SMALL.start, until=date(2024, 2, 10))
    assert more["orders"] == 10
    assert not list(tmp_path.rglob("*.tmp"))


def test_loader_is_incremental_and_idempotent(small_sim, tmp_path):
    landing, wh = tmp_path / "landing", tmp_path / "wh.duckdb"
    write_landing(small_sim, landing, SMALL.start, until=date(2024, 2, 15))
    r1 = load_incremental(landing, wh)
    rows_after_first = _count(wh, "raw.orders")
    assert r1.rows_loaded["orders"] == rows_after_first > 0

    r2 = load_incremental(landing, wh)
    assert sum(r2.files_loaded.values()) == 0
    assert _count(wh, "raw.orders") == rows_after_first

    write_landing(small_sim, landing, SMALL.start)
    r3 = load_incremental(landing, wh)
    assert r3.files_loaded["orders"] == 14 + 31  # Feb 16-29 (leap year) + March
    expected = len(small_sim.orders)
    assert _count(wh, "raw.orders") == expected


def test_loader_detects_files_modified_after_load(small_sim, tmp_path):
    landing, wh = tmp_path / "landing", tmp_path / "wh.duckdb"
    write_landing(small_sim, landing, SMALL.start, until=date(2024, 1, 5))
    load_incremental(landing, wh)
    f = landing / "orders" / "dt=2024-01-02" / "orders.csv"
    f.write_text(f.read_text() + f.read_text().splitlines()[1] + "\n")
    os.utime(f, None)
    report = load_incremental(landing, wh)
    assert report.files_changed_since_load == ["orders/dt=2024-01-02/orders.csv"]


def test_loader_records_lineage(small_sim, tmp_path):
    landing, wh = tmp_path / "landing", tmp_path / "wh.duckdb"
    write_landing(small_sim, landing, SMALL.start, until=date(2024, 1, 3))
    report = load_incremental(landing, wh)
    with duckdb.connect(str(wh), read_only=True) as con:
        files = con.execute(
            "SELECT DISTINCT _source_file, _load_id FROM raw.orders ORDER BY 1"
        ).fetchall()
    assert [f for f, _ in files] == [f"orders/dt=2024-01-0{d}/orders.csv" for d in (1, 2, 3)]
    assert {lid for _, lid in files} == {report.load_id}


def test_committed_seeds_match_reference_data():
    for name, frame in seed_frames().items():
        committed = pd.read_csv(DBT_DIR / "seeds" / f"{name}.csv")
        expected = pd.read_csv(pd.io.common.StringIO(frame.to_csv(index=False)))
        pd.testing.assert_frame_equal(committed, expected, obj=name)
