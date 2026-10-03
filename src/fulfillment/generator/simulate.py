"""Deterministic simulation of an e-commerce order-fulfilment operation in India.

The output imitates what a data team actually receives from an OLTP system: daily
change-data-capture (CDC) extracts, where every status change of an order produces a
new row version, plus the usual production problems:

* late-arriving records  - a version lands in a later day's file than it happened
* exact duplicates       - the same version re-sent by the extractor
* dirty dimensions       - inconsistent state spellings ("Tamilnadu", "TN", "Orissa")
* clock-skew anomalies   - delivered_at earlier than shipped_at for a few orders
* slowly changing data   - customers move between states over time

Lifecycle timings are driven by payment method (COD needs verification), hub load,
sale-event congestion, region distance, remoteness, monsoon and courier speed, so the
resulting KPIs (approval ~10-15 h, delivery ~4-15 days by state) carry real signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from fulfillment.generator import reference as ref

STATUS_ORDER = ["created", "approved", "shipped", "delivered", "returned", "cancelled", "rto"]


@dataclass(frozen=True)
class SimulationConfig:
    start: date = date(2024, 1, 1)
    end: date = date(2025, 12, 31)
    orders_per_day: float = 160.0  # baseline at `start`, before seasonality
    yearly_growth: float = 0.35
    seed: int = 42
    late_arrival_rate: float = 0.02
    duplicate_rate: float = 0.005
    clock_skew_rate: float = 0.003
    dirty_state_rate: float = 0.06
    customer_move_rate: float = 0.03


@dataclass
class SimulationResult:
    customers: pd.DataFrame  # CDC versions
    products: pd.DataFrame  # full snapshot
    sellers: pd.DataFrame  # full snapshot
    orders: pd.DataFrame  # CDC versions (incl. duplicates / late rows)
    order_items: pd.DataFrame
    payments: pd.DataFrame
    truth: pd.DataFrame  # one clean row per order - used only by tests


# --------------------------------------------------------------------------- helpers
def _daily_volume(cfg: SimulationConfig, rng: np.random.Generator) -> pd.DataFrame:
    days = pd.date_range(cfg.start, cfg.end, freq="D")
    t_years = (days - days[0]).days / 365.0
    base = cfg.orders_per_day * (1 + cfg.yearly_growth) ** t_years
    weekday = np.where(days.dayofweek >= 5, 1.15, 1.0)
    uplift = np.ones(len(days))
    sale_name = np.full(len(days), None, dtype=object)
    for name, month, start_day, length, factor in ref.SALE_EVENTS:
        for year in sorted(set(days.year)):
            s = pd.Timestamp(year=year, month=month, day=start_day)
            mask = (days >= s) & (days < s + pd.Timedelta(days=length))
            uplift[mask] = np.maximum(uplift[mask], factor)
            sale_name[mask] = name
    expected = base * weekday * uplift
    counts = rng.poisson(expected)
    return pd.DataFrame({"day": days, "orders": counts, "sale_event": sale_name, "uplift": uplift})


def _lognormal(rng, median, sigma, size):
    return rng.lognormal(np.log(median), sigma, size)


def _choice(rng, items, weights, size):
    w = np.asarray(weights, dtype=float)
    return rng.choice(len(items), size=size, p=w / w.sum())


# --------------------------------------------------------------------------- entities
def _customers(cfg, rng, n_customers, horizon_end) -> tuple[pd.DataFrame, pd.DataFrame]:
    states = pd.DataFrame(ref.STATES, columns=["state", "code", "region", "remoteness", "weight"])
    idx = _choice(rng, states.index, states.weight, n_customers)
    signup = pd.to_datetime(cfg.start) - pd.to_timedelta(rng.integers(0, 900, n_customers), "D")
    base = pd.DataFrame(
        {
            "customer_id": [f"C{i:07d}" for i in range(1, n_customers + 1)],
            "state": states.state.to_numpy()[idx],
            "pincode": rng.integers(110001, 855117, n_customers).astype(str),
            "signup_at": signup,
        }
    )
    base["updated_at"] = base["signup_at"]

    # SCD: some customers move to another state during the horizon.
    movers = base.sample(frac=cfg.customer_move_rate, random_state=cfg.seed).copy()
    span = (pd.Timestamp(horizon_end) - pd.Timestamp(cfg.start)).days
    movers["updated_at"] = pd.Timestamp(cfg.start) + pd.to_timedelta(
        rng.integers(30, span, len(movers)), "D"
    )
    movers["state"] = states.state.to_numpy()[
        _choice(rng, states.index, states.weight, len(movers))
    ]
    movers["pincode"] = rng.integers(110001, 855117, len(movers)).astype(str)

    versions = pd.concat([base, movers], ignore_index=True)
    # Dirty spellings in the source system
    dirty = rng.random(len(versions)) < cfg.dirty_state_rate
    versions["state_raw"] = versions["state"]
    for i in np.flatnonzero(dirty):
        aliases = ref.STATE_ALIASES.get(versions.at[i, "state"])
        if aliases:
            versions.at[i, "state_raw"] = aliases[rng.integers(len(aliases))]
    versions.loc[rng.random(len(versions)) < 0.01, "pincode"] = None
    return base, versions


def _catalogue(cfg, rng, n_products=2500, n_sellers=180):
    cats = pd.DataFrame(ref.CATEGORIES, columns=["category", "share", "pmin", "pmax", "kg"])
    ci = _choice(rng, cats.index, cats.share, n_products)
    lo, hi = cats.pmin.to_numpy()[ci], cats.pmax.to_numpy()[ci]
    price = np.round(np.exp(rng.uniform(np.log(lo), np.log(hi))) / 10) * 10 - 1
    hubs = pd.DataFrame(ref.HUBS, columns=["hub_id", "hub_state", "hub_region"])
    sellers = pd.DataFrame(
        {
            "seller_id": [f"S{i:05d}" for i in range(1, n_sellers + 1)],
            "seller_name": [f"Seller {i:03d}" for i in range(1, n_sellers + 1)],
            "hub_id": hubs.hub_id.to_numpy()[rng.integers(0, len(hubs), n_sellers)],
            "onboarded_at": pd.Timestamp(cfg.start)
            - pd.to_timedelta(rng.integers(30, 1500, n_sellers), "D"),
        }
    )
    products = pd.DataFrame(
        {
            "product_id": [f"P{i:06d}" for i in range(1, n_products + 1)],
            "category": cats.category.to_numpy()[ci],
            "list_price": price,
            "weight_kg": np.round(cats.kg.to_numpy()[ci] * rng.uniform(0.6, 1.6, n_products), 2),
            "seller_id": sellers.seller_id.to_numpy()[rng.integers(0, n_sellers, n_products)],
        }
    )
    return products, sellers.merge(hubs, on="hub_id")


# ----------------------------------------------------------------------- simulation
def simulate(cfg: SimulationConfig | None = None) -> SimulationResult:
    cfg = cfg or SimulationConfig()
    rng = np.random.default_rng(cfg.seed)
    horizon_end = pd.Timestamp(cfg.end) + pd.Timedelta(days=1)  # exclusive

    volume = _daily_volume(cfg, rng)
    n_orders = int(volume.orders.sum())
    customers_base, customer_versions = _customers(
        cfg, rng, max(1000, int(n_orders * 0.42)), horizon_end
    )
    products, sellers = _catalogue(cfg, rng)

    # ---- order headers -------------------------------------------------------
    day = np.repeat(volume.day.to_numpy(), volume.orders.to_numpy())
    uplift = np.repeat(volume.uplift.to_numpy(), volume.orders.to_numpy())
    sale = np.repeat(volume.sale_event.to_numpy(), volume.orders.to_numpy())
    # intraday: evening-heavy mixture
    hour = np.where(
        rng.random(n_orders) < 0.65, rng.normal(20.5, 2.2, n_orders), rng.uniform(7, 23, n_orders)
    )
    seconds = np.clip(hour, 0, 23.99) * 3600
    purchase_at = pd.to_datetime(day) + pd.to_timedelta(seconds.astype(int), "s")

    # repeat customers: Zipf-like popularity
    pop = 1 / np.arange(1, len(customers_base) + 1) ** 0.6
    cust_idx = rng.choice(len(customers_base), size=n_orders, p=pop / pop.sum())
    customer_id = customers_base.customer_id.to_numpy()[cust_idx]

    # state at time of purchase (point-in-time, respects customer moves)
    cv = customer_versions.sort_values("updated_at")
    orders_tmp = pd.DataFrame({"customer_id": customer_id, "purchase_at": purchase_at})
    orders_tmp["_row"] = np.arange(n_orders)
    pit = pd.merge_asof(
        orders_tmp.sort_values("purchase_at"),
        cv[["customer_id", "updated_at", "state"]].rename(columns={"updated_at": "purchase_at"}),
        on="purchase_at",
        by="customer_id",
        direction="backward",
    ).sort_values("_row")
    cust_state = np.where(
        pit["state"].isna(), customers_base.state.to_numpy()[cust_idx], pit["state"].to_numpy()
    )

    states = pd.DataFrame(ref.STATES, columns=["state", "code", "region", "remoteness", "weight"])
    st = states.set_index("state").loc[cust_state]
    cust_region, remoteness = st.region.to_numpy(), st.remoteness.to_numpy()

    pm_names = [p for p, _ in ref.PAYMENT_METHODS]
    payment_method = np.array(pm_names)[
        _choice(rng, pm_names, [w for _, w in ref.PAYMENT_METHODS], n_orders)
    ]
    is_cod = payment_method == "COD"

    # ---- items ---------------------------------------------------------------
    n_items = rng.choice([1, 2, 3, 4], size=n_orders, p=[0.62, 0.24, 0.10, 0.04])
    order_ids = np.array([f"ORD{i:08d}" for i in range(1, n_orders + 1)])
    item_order = np.repeat(np.arange(n_orders), n_items)
    prod_idx = rng.integers(0, len(products), len(item_order))
    items = pd.DataFrame(
        {
            "order_id": order_ids[item_order],
            "order_item_seq": np.concatenate([np.arange(1, k + 1) for k in n_items]),
            "product_id": products.product_id.to_numpy()[prod_idx],
            "seller_id": products.seller_id.to_numpy()[prod_idx],
            "quantity": rng.choice([1, 1, 1, 2], size=len(item_order)),
        }
    )
    discount = np.where(
        np.repeat(uplift, n_items) > 1,
        rng.uniform(0.2, 0.55, len(items)),
        rng.uniform(0, 0.25, len(items)),
    )
    items["unit_price"] = np.round(products.list_price.to_numpy()[prod_idx] * (1 - discount), 2)
    items["created_at"] = purchase_at.to_numpy()[item_order]

    # the shipment leaves from the first item's seller hub
    first_seller = items.groupby("order_id", sort=False)["seller_id"].first().reindex(order_ids)
    seller_hub = sellers.set_index("seller_id").loc[first_seller.to_numpy()]
    hub_region = seller_hub.hub_region.to_numpy()
    hub_id = seller_hub.hub_id.to_numpy()

    dist = np.array(
        [ref.region_distance(a, b) for a, b in zip(hub_region, cust_region, strict=True)]
    )
    remote_extra = np.select([remoteness == 1, remoteness == 2], [0.0, 1.5], 4.0)
    promise_extra = np.select([remoteness == 1, remoteness == 2], [0, 2], 5)

    courier_tbl = pd.DataFrame(ref.COURIERS, columns=["courier", "speed", "reliability"])
    ci = rng.integers(0, len(courier_tbl), n_orders)
    courier = courier_tbl.courier.to_numpy()[ci]
    speed = courier_tbl.speed.to_numpy()[ci]
    reliability = courier_tbl.reliability.to_numpy()[ci]

    # ---- lifecycle timings -----------------------------------------------------
    weekend = pd.DatetimeIndex(purchase_at).dayofweek.to_numpy() >= 5
    congestion = np.where(uplift > 1, 1 + (uplift - 1) * 0.25, 1.0)
    approval_h = (
        np.where(is_cod, _lognormal(rng, 13, 0.6, n_orders), _lognormal(rng, 6.5, 0.75, n_orders))
        * np.where(weekend, 1.3, 1.0)
        * congestion
    )
    handover_h = _lognormal(rng, 20, 0.5, n_orders) * congestion
    month = pd.DatetimeIndex(purchase_at).month.to_numpy()
    monsoon = np.where(np.isin(month, [7, 8]) & (remoteness >= 2), 1.3, 1.0)
    transit_d = (
        (3 + 1.8 * dist + remote_extra)
        * speed
        * congestion
        * monsoon
        * _lognormal(rng, 1.0, 0.3, n_orders)
    )
    # The promise shown at checkout: knows distance and remoteness, not congestion.
    promised_days = np.ceil(6.5 + 2.0 * dist + promise_extra).astype(int)

    approved_at = purchase_at + pd.to_timedelta(approval_h, "h")
    shipped_at = approved_at + pd.to_timedelta(handover_h, "h")
    delivered_at = shipped_at + pd.to_timedelta(transit_d, "D")
    estimated_delivery = (
        pd.DatetimeIndex(purchase_at).normalize() + pd.to_timedelta(promised_days, "D")
    ).date

    # outcomes
    u = rng.random(n_orders)
    cancel_p = np.where(is_cod, 0.08, 0.035)
    cancelled = u < cancel_p
    cancel_at = purchase_at + pd.to_timedelta(
        rng.uniform(0.5, 1.0, n_orders) * approval_h * 1.5, "h"
    )
    rto_p = np.where(is_cod, 0.03, 0.008) + (1 - reliability) * 0.2
    rto = (~cancelled) & (rng.random(n_orders) < rto_p)
    rto_at = delivered_at + pd.to_timedelta(rng.uniform(3, 7, n_orders), "D")
    returned = (~cancelled) & (~rto) & (rng.random(n_orders) < 0.07)
    returned_at = delivered_at + pd.to_timedelta(rng.uniform(2, 12, n_orders), "D")

    truth = pd.DataFrame(
        {
            "order_id": order_ids,
            "customer_id": customer_id,
            "customer_state": cust_state,
            "hub_id": hub_id,
            "courier": courier,
            "payment_method": payment_method,
            "purchase_at": purchase_at,
            "approved_at": approved_at,
            "shipped_at": shipped_at,
            "delivered_at": delivered_at,
            "estimated_delivery_date": estimated_delivery,
            "cancelled": cancelled,
            "cancel_at": cancel_at,
            "rto": rto,
            "rto_at": rto_at,
            "returned": returned,
            "returned_at": returned_at,
            "sale_event": sale,
        }
    )

    orders = _order_versions(truth, cfg, rng, horizon_end)
    payments = _payments(truth, items, rng, horizon_end)
    return SimulationResult(
        customers=customer_versions.drop(columns=["state"]).rename(columns={"state_raw": "state"}),
        products=products,
        sellers=sellers[["seller_id", "seller_name", "hub_id", "hub_state", "onboarded_at"]],
        orders=orders,
        order_items=items,
        payments=payments,
        truth=truth,
    )


def _order_versions(truth: pd.DataFrame, cfg, rng, horizon_end) -> pd.DataFrame:
    """Explode each order's lifecycle into CDC row versions."""
    base_cols = [
        "order_id",
        "customer_id",
        "hub_id",
        "courier",
        "payment_method",
        "purchase_at",
        "estimated_delivery_date",
    ]
    frames = []
    t = truth

    def version(mask, status, at, approved, shipped, delivered, closed):
        f = t.loc[mask, base_cols].copy()
        f["order_status"] = status
        f["approved_at"] = approved[mask] if approved is not None else pd.NaT
        f["shipped_at"] = shipped[mask] if shipped is not None else pd.NaT
        f["delivered_at"] = delivered[mask] if delivered is not None else pd.NaT
        f["closed_at"] = closed[mask] if closed is not None else pd.NaT
        f["updated_at"] = at[mask]
        frames.append(f)

    live = ~t.cancelled
    nat = pd.Series(pd.NaT, index=t.index)
    version(t.index == t.index, "created", t.purchase_at, None, None, None, None)
    # cancelled before approval vs after approval
    cancel_after_approval = t.cancelled & (t.cancel_at > t.approved_at)
    version(
        live | cancel_after_approval, "approved", t.approved_at, t.approved_at, None, None, None
    )
    version(
        t.cancelled,
        "cancelled",
        t.cancel_at,
        t.approved_at.where(cancel_after_approval, nat),
        None,
        None,
        t.cancel_at,
    )
    version(live, "shipped", t.shipped_at, t.approved_at, t.shipped_at, None, None)
    delivered_ok = live & ~t.rto
    # clock-skew anomaly: delivered timestamp before shipped
    skew = delivered_ok & (rng.random(len(t)) < cfg.clock_skew_rate)
    delivered_ts = t.delivered_at.where(~skew, t.shipped_at - pd.to_timedelta(5, "h"))
    version(
        delivered_ok, "delivered", t.delivered_at, t.approved_at, t.shipped_at, delivered_ts, None
    )
    version(t.rto, "rto", t.rto_at, t.approved_at, t.shipped_at, None, t.rto_at)
    version(
        t.returned & delivered_ok,
        "returned",
        t.returned_at,
        t.approved_at,
        t.shipped_at,
        delivered_ts,
        t.returned_at,
    )

    v = pd.concat(frames, ignore_index=True)
    v = v[v.updated_at < horizon_end]  # the future hasn't happened yet

    # extract date = when the row lands in a file; some arrive late
    late = rng.random(len(v)) < cfg.late_arrival_rate
    delay = pd.to_timedelta(np.where(late, rng.integers(1, 4, len(v)), 0), "D")
    v["_extract_date"] = (v.updated_at.dt.normalize() + delay).dt.date
    dupes = v.sample(frac=cfg.duplicate_rate, random_state=cfg.seed)
    v = pd.concat([v, dupes], ignore_index=True)
    v = v[pd.to_datetime(v["_extract_date"]) < horizon_end]
    return v.sort_values(["_extract_date", "updated_at", "order_id"], ignore_index=True)


def _payments(truth, items, rng, horizon_end) -> pd.DataFrame:
    gross = (items.unit_price * items.quantity).groupby(items.order_id).sum()
    t = truth.set_index("order_id")
    amount = gross.reindex(t.index).to_numpy()
    shipping = np.where(amount < 499, 49.0, 0.0)
    charge = pd.DataFrame(
        {
            "payment_id": [f"PAY{i:09d}" for i in range(1, len(t) + 1)],
            "order_id": t.index,
            "payment_type": "charge",
            "payment_method": t.payment_method.to_numpy(),
            "amount": np.round(amount + shipping, 2),
            "created_at": t.purchase_at.to_numpy(),
        }
    )
    # COD is collected on delivery, not at purchase
    cod = charge.payment_method.eq("COD").to_numpy()
    delivered_ok = (~t.cancelled & ~t.rto).to_numpy()
    charge = charge[~cod | delivered_ok].copy()
    charge.loc[charge.payment_method.eq("COD"), "created_at"] = t.loc[
        charge.loc[charge.payment_method.eq("COD"), "order_id"], "delivered_at"
    ].to_numpy()

    refund_mask = (t.cancelled | t.returned | t.rto).to_numpy() & (
        t.payment_method != "COD"
    ).to_numpy()
    refund_mask |= (t.returned & ~t.rto & ~t.cancelled).to_numpy()  # COD returns refunded too
    r = t[refund_mask]
    refund_at = np.where(r.cancelled, r.cancel_at, np.where(r.rto, r.rto_at, r.returned_at))
    refunds = pd.DataFrame(
        {
            "payment_id": [f"REF{i:09d}" for i in range(1, len(r) + 1)],
            "order_id": r.index,
            "payment_type": "refund",
            "payment_method": r.payment_method.to_numpy(),
            "amount": -np.round(gross.reindex(r.index).to_numpy(), 2),
            "created_at": pd.to_datetime(refund_at) + pd.to_timedelta(1, "D"),
        }
    )
    p = pd.concat([charge, refunds], ignore_index=True)
    return p[p.created_at < horizon_end].sort_values("created_at", ignore_index=True)


def date_range(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)
