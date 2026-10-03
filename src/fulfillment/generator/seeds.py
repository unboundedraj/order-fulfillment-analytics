"""Export reference data to dbt seeds so generator and warehouse share one source of truth.

tests/test_seeds.py fails if the committed seed files drift from reference.py.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from fulfillment.generator import reference as ref


def seed_frames(years: tuple[int, ...] = (2024, 2025)) -> dict[str, pd.DataFrame]:
    states = pd.DataFrame(
        [(s, c, r, t) for s, c, r, t, _ in ref.STATES],
        columns=["state", "state_code", "region", "remoteness_tier"],
    )
    alias_rows = [(s.lower(), s) for s, *_ in ref.STATES]
    alias_rows += [(c.lower(), s) for s, c, *_ in ref.STATES]
    for state, aliases in ref.STATE_ALIASES.items():
        alias_rows += [(a.lower(), state) for a in aliases]
    aliases = (
        pd.DataFrame(alias_rows, columns=["alias", "state"])
        .drop_duplicates("alias")
        .sort_values("alias", ignore_index=True)
    )
    events = []
    for name, month, start_day, length, _ in ref.SALE_EVENTS:
        for y in years:
            start = pd.Timestamp(year=y, month=month, day=start_day)
            events.append((name, start.date(), (start + pd.Timedelta(days=length - 1)).date()))
    calendar = pd.DataFrame(events, columns=["sale_event", "start_date", "end_date"]).sort_values(
        "start_date", ignore_index=True
    )
    hubs = pd.DataFrame(ref.HUBS, columns=["hub_id", "hub_state", "hub_region"])
    couriers = pd.DataFrame([(c,) for c, *_ in ref.COURIERS], columns=["courier"])
    return {
        "ref_states": states,
        "state_aliases": aliases,
        "sale_calendar": calendar,
        "ref_hubs": hubs,
        "ref_couriers": couriers,
    }


def export_seeds(seed_dir: Path) -> list[Path]:
    seed_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, frame in seed_frames().items():
        path = seed_dir / f"{name}.csv"
        frame.to_csv(path, index=False, lineterminator="\n")
        written.append(path)
    return written
