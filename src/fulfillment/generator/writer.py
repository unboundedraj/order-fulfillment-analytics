"""Write a simulation to the landing zone as daily extract files.

    landing/
      catalog/products.csv, sellers.csv          full snapshots
      customers/dt=YYYY-MM-DD/customers.csv      CDC versions (initial load on day 1)
      orders/dt=YYYY-MM-DD/orders.csv            CDC versions, incl. late + duplicate rows
      order_items/dt=YYYY-MM-DD/order_items.csv
      payments/dt=YYYY-MM-DD/payments.csv

`until` lets you "release" days one at a time to exercise incremental loading:
the simulation is deterministic, so already-written days are byte-identical and
are skipped.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from fulfillment.generator.simulate import SimulationResult


def _write_daily(
    frame: pd.DataFrame, by: pd.Series, entity: str, landing: Path, until: date | None
) -> int:
    written = 0
    days = pd.to_datetime(by).dt.date
    for d, part in frame.groupby(days, sort=True):
        if until and d > until:
            break
        target = landing / entity / f"dt={d.isoformat()}" / f"{entity}.csv"
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        part.to_csv(tmp, index=False, date_format="%Y-%m-%d %H:%M:%S")
        tmp.replace(target)  # atomic publish - loaders never see half-written files
        written += 1
    return written


def write_landing(
    result: SimulationResult, landing: Path, start: date, until: date | None = None
) -> dict[str, int]:
    landing.mkdir(parents=True, exist_ok=True)
    catalog = landing / "catalog"
    catalog.mkdir(exist_ok=True)
    result.products.to_csv(catalog / "products.csv", index=False)
    result.sellers.to_csv(catalog / "sellers.csv", index=False, date_format="%Y-%m-%d %H:%M:%S")

    customers = result.customers.copy()
    # everything that existed before the horizon arrives in the initial day-1 load
    cust_day = customers["updated_at"].where(
        customers["updated_at"] >= pd.Timestamp(start), pd.Timestamp(start)
    )
    orders = result.orders.drop(columns=["_extract_date"])
    return {
        "customers": _write_daily(customers, cust_day, "customers", landing, until),
        "orders": _write_daily(orders, result.orders["_extract_date"], "orders", landing, until),
        "order_items": _write_daily(
            result.order_items, result.order_items["created_at"], "order_items", landing, until
        ),
        "payments": _write_daily(
            result.payments, result.payments["created_at"], "payments", landing, until
        ),
    }
