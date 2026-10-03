import pandas as pd

from fulfillment.generator.simulate import simulate
from tests.conftest import SMALL


def test_simulation_is_deterministic(small_sim):
    again = simulate(SMALL)
    pd.testing.assert_frame_equal(small_sim.orders, again.orders)
    pd.testing.assert_frame_equal(small_sim.payments, again.payments)


def test_cdc_versions_follow_lifecycle(small_sim):
    o = small_sim.orders.drop_duplicates()
    created = set(o.loc[o.order_status == "created", "order_id"])
    assert created == set(o.order_id), "every order starts with a 'created' version"
    shipped = o[o.order_status == "shipped"]
    assert shipped.shipped_at.notna().all() and shipped.delivered_at.isna().all()


def test_injected_data_problems_are_present(small_sim):
    o = small_sim.orders
    dupes = o.duplicated().sum()
    late = (pd.to_datetime(o._extract_date) > o.updated_at.dt.normalize()).mean()
    assert dupes > 0
    assert 0.005 < late < 0.05
    from fulfillment.generator.reference import STATES

    canonical = {s for s, *_ in STATES}
    dirty = ~small_sim.customers.state.isin(canonical)
    assert 0.02 < dirty.mean() < 0.10  # alias spellings like "Tamilnadu", "Orissa"


def test_kpis_are_calibrated(full_sim):
    t = full_sim.truth
    approval_h = (t.approved_at - t.purchase_at).dt.total_seconds() / 3600
    assert 10 <= approval_h.mean() <= 15  # matches the original dashboard's 10-15 h band

    d = t[~t.cancelled & ~t.rto]
    days = (d.delivered_at - d.purchase_at).dt.total_seconds() / 86400
    by_state = days.groupby(d.customer_state).mean()
    assert by_state.min() >= 7 and by_state.max() <= 18
    assert by_state["Maharashtra"] < by_state["Assam"]  # remoteness matters

    late = d.delivered_at.dt.normalize() > pd.to_datetime(d.estimated_delivery_date)
    on_sale = d.sale_event.notna()
    assert late[~on_sale].mean() < 0.15 < late[on_sale].mean()  # sales congest logistics


def test_payments_never_exceed_basket(small_sim):
    p = small_sim.payments
    charges = p[p.payment_type == "charge"].groupby("order_id").amount.sum()
    refunds = -p[p.payment_type == "refund"].groupby("order_id").amount.sum()
    joined = pd.concat([charges, refunds], axis=1, keys=["c", "r"]).dropna()
    assert len(joined) > 0
    assert (joined.r <= joined.c + 0.01).all()  # never refund more than was collected
