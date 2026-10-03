"""Fulfillment & Delivery dashboard (Streamlit + Plotly over the DuckDB warehouse).

    streamlit run dashboard/app.py

Reads only from the `core` and `kpi` schemas built by dbt. All filtered aggregates are
computed in DuckDB, so the page stays fast on the full dataset.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

WAREHOUSE = Path(
    os.environ.get(
        "FULFILLMENT_WAREHOUSE", Path(__file__).resolve().parents[1] / "data" / "warehouse.duckdb"
    )
)

# Palette: categorical slots in fixed order, status colours reserved for SLA state.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
STATUS = {"healthy": "#0ca30c", "at risk": "#fab219", "critical": "#d03b3b"}
STATUS_ICON = {"healthy": "●", "at risk": "▲", "critical": "■"}
INK, INK_2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
SURFACE = "#fcfcfb"

st.set_page_config(page_title="Fulfillment & Delivery", layout="wide")


# ----------------------------------------------------------------------------- data
@st.cache_resource
def connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(WAREHOUSE), read_only=True)


@st.cache_data(ttl=300)
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    return connection().execute(sql, list(params)).df()


def base_layout(fig: go.Figure, height: int = 320, **kw) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", color=INK_2, size=12),
        hoverlabel=dict(bgcolor="white", font_color=INK, bordercolor=GRID),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font_color=INK_2),
        bargap=0.25,
        **kw,
    )
    fig.update_xaxes(showgrid=False, linecolor=AXIS, tickfont_color=MUTED, zeroline=False)
    fig.update_yaxes(
        gridcolor=GRID, gridwidth=1, linecolor=AXIS, tickfont_color=MUTED, zeroline=False
    )
    return fig


if not WAREHOUSE.exists():
    st.error(f"Warehouse not found at {WAREHOUSE}. Run `fulfillment run` first.")
    st.stop()

bounds = query("SELECT min(order_date) AS lo, max(order_date) AS hi FROM core.fct_orders")
lo, hi = bounds.lo[0].date(), bounds.hi[0].date()
regions = query("SELECT DISTINCT region FROM core.dim_geography ORDER BY 1").region.tolist()

# ------------------------------------------------------------------------- header
st.title("Order Fulfillment & Delivery")
st.caption(
    "Simulated e-commerce marketplace · CDC feed → dbt/DuckDB warehouse · "
    f"data through {hi:%d %b %Y}"
)

f1, f2, f3 = st.columns([2, 3, 2])
with f1:
    default_start = max(lo, date(hi.year, 1, 1))
    picked = st.date_input("Order date", (default_start, hi), min_value=lo, max_value=hi)
with f2:
    region_sel = st.multiselect("Destination region", regions, default=regions)
with f3:
    pm_sel = st.selectbox("Payment", ["All", "Prepaid", "COD"])

start, end = picked if isinstance(picked, tuple) and len(picked) == 2 else (default_start, hi)
regions_sql = region_sel or regions
pm_clause = {
    "All": "",
    "Prepaid": "AND payment_method <> 'COD'",
    "COD": "AND payment_method = 'COD'",
}[pm_sel]
WHERE = "WHERE order_date BETWEEN ? AND ? AND list_contains(?, customer_region) " + pm_clause
PARAMS = (start, end, regions_sql)

# ------------------------------------------------------------------------ KPI tiles
k = query(
    f"""
    SELECT count(*) AS orders,
           avg(approval_hours) AS approval_h,
           avg(delivery_days) AS delivery_d,
           avg(CASE WHEN is_delivered THEN (NOT is_late)::INT END) AS on_time,
           avg(is_rto::INT) AS rto,
           sum(net_revenue) AS revenue
    FROM core.fct_orders {WHERE}
    """,
    PARAMS,
).iloc[0]

if not k.orders:
    st.warning("No orders match the current filters.")
    st.stop()

t = st.columns(5)
t[0].metric("Orders", f"{int(k.orders):,}")
t[1].metric("Avg approval time", f"{k.approval_h:.1f} h")
t[2].metric("Avg order-to-door", f"{k.delivery_d:.1f} days")
t[3].metric("On-time delivery", f"{k.on_time:.1%}")
t[4].metric("Net revenue", f"₹{k.revenue / 1e7:.2f} Cr")

# --------------------------------------------------------------------- trends
st.subheader("Trend")
trend = query(
    f"""
    SELECT date_trunc('week', order_date) AS week,
           count(*) AS orders,
           avg(CASE WHEN is_delivered THEN (NOT is_late)::INT END) AS on_time,
           avg(approval_hours) AS approval_h
    FROM core.fct_orders {WHERE}
    GROUP BY 1 ORDER BY 1
    """,
    PARAMS,
)
c1, c2 = st.columns(2)
with c1:
    st.markdown("**On-time delivery rate, weekly**")
    # Recent orders are still in flight: only the fast ones have been delivered, which
    # would inflate on-time. Plot settled weeks only.
    settled = trend[pd.to_datetime(trend.week) <= pd.Timestamp(hi) - pd.Timedelta(days=28)]
    fig = go.Figure(
        go.Scatter(
            x=settled.week,
            y=settled.on_time,
            mode="lines",
            line=dict(color=SERIES[0], width=2),
            hovertemplate="Week of %{x|%d %b %Y}<br>On-time %{y:.1%}<extra></extra>",
        )
    )
    fig.update_yaxes(tickformat=".0%", rangemode="tozero")
    st.plotly_chart(base_layout(fig, hovermode="x"), width="stretch")
    st.caption("The last 4 weeks are hidden: those orders are still in flight.")
with c2:
    st.markdown("**Orders per week**")
    fig = go.Figure(
        go.Bar(
            x=trend.week,
            y=trend.orders,
            marker=dict(color=SERIES[0], cornerradius=4),
            hovertemplate="Week of %{x|%d %b %Y}<br>%{y:,} orders<extra></extra>",
        )
    )
    st.plotly_chart(base_layout(fig), width="stretch")

# -------------------------------------------------------------- state scorecard
st.subheader("Where are we late?")
states = query(
    f"""
    WITH s AS (
        SELECT customer_state AS state,
               count(*) AS orders,
               avg(delivery_days) AS delivery_d,
               avg(CASE WHEN is_delivered THEN (NOT is_late)::INT END) AS on_time,
               avg(approval_hours) AS approval_h,
               avg(processing_hours) AS processing_h,
               avg(transit_days) * 24 AS transit_h
        FROM core.fct_orders {WHERE}
        GROUP BY 1
    ), n AS (
        SELECT avg(CASE WHEN is_delivered THEN (NOT is_late)::INT END) AS nat
        FROM core.fct_orders {WHERE}
    )
    SELECT s.*, CASE WHEN on_time < nat - 0.10 THEN 'critical'
                     WHEN on_time < nat - 0.03 THEN 'at risk'
                     ELSE 'healthy' END AS health
    FROM s, n
    WHERE orders >= 30
    ORDER BY on_time
    """,
    PARAMS + PARAMS,
)
c1, c2 = st.columns(2)
with c1:
    st.markdown("**On-time rate by destination state** (states with ≥ 30 orders)")
    fig = go.Figure()
    for health in ["critical", "at risk", "healthy"]:
        d = states[states.health == health]
        fig.add_bar(
            y=d.state,
            x=d.on_time,
            orientation="h",
            name=f"{STATUS_ICON[health]} {health}",
            marker=dict(color=STATUS[health], cornerradius=4),
            customdata=d[["orders", "delivery_d"]],
            hovertemplate="%{y}<br>On-time %{x:.1%}<br>%{customdata[0]:,} orders · "
            "%{customdata[1]:.1f} days avg<extra></extra>",
        )
    fig.update_yaxes(categoryorder="array", categoryarray=states.state.tolist(), showgrid=False)
    fig.update_xaxes(tickformat=".0%", showgrid=True, gridcolor=GRID)
    st.plotly_chart(base_layout(fig, height=640, barmode="overlay"), width="stretch")
with c2:
    st.markdown("**Where the time goes: hours per stage** (slowest 12 states)")
    slow = states.sort_values("delivery_d", ascending=False).head(12).iloc[::-1]
    fig = go.Figure()
    for i, (col, label) in enumerate(
        [
            ("approval_h", "Approval"),
            ("processing_h", "Warehouse processing"),
            ("transit_h", "Last-mile transit"),
        ]
    ):
        fig.add_bar(
            y=slow.state,
            x=slow[col],
            orientation="h",
            name=label,
            marker=dict(color=SERIES[i], line=dict(color=SURFACE, width=2)),
            hovertemplate=f"%{{y}}<br>{label}: %{{x:.0f}} h<extra></extra>",
        )
    fig.update_yaxes(showgrid=False)
    fig.update_xaxes(showgrid=True, gridcolor=GRID, title_text="hours", title_font_color=MUTED)
    st.plotly_chart(
        base_layout(fig, height=640, barmode="stack", legend_traceorder="normal"), width="stretch"
    )

# --------------------------------------------------------------------- couriers
st.subheader("Courier SLA performance")
couriers = query(
    f"""
    SELECT courier,
           CASE WHEN sale_event IS NULL THEN 'Normal days' ELSE 'Sale days' END AS period,
           avg(CASE WHEN is_delivered THEN (NOT is_late)::INT END) AS on_time,
           avg(transit_days) AS transit_d,
           count(*) AS orders
    FROM core.fct_orders {WHERE} AND shipped_at IS NOT NULL
    GROUP BY ALL
    """,
    PARAMS,
)
order = (
    couriers[couriers.period == "Normal days"]
    .sort_values("on_time", ascending=False)
    .courier.tolist()
)
fig = go.Figure()
for i, period in enumerate(["Normal days", "Sale days"]):
    d = couriers[couriers.period == period].set_index("courier").reindex(order).reset_index()
    fig.add_bar(
        x=d.courier,
        y=d.on_time,
        name=period,
        marker=dict(color=SERIES[i], cornerradius=4, line=dict(color=SURFACE, width=2)),
        customdata=d[["transit_d", "orders"]],
        hovertemplate="%{x} · " + period + "<br>On-time %{y:.1%}<br>"
        "Transit %{customdata[0]:.1f} days · %{customdata[1]:,} shipments<extra></extra>",
    )
fig.update_yaxes(tickformat=".0%", rangemode="tozero")
st.plotly_chart(base_layout(fig, barmode="group"), width="stretch")

# ------------------------------------------------------------------ sale events
st.subheader("Cost of sale events")
st.caption("Each sale event compared with the non-sale 28 days before it (all regions).")
sales = query("SELECT * FROM kpi.mart_sale_event_impact ORDER BY start_date")
sales["start_date"] = pd.to_datetime(sales.start_date).dt.date
sales["end_date"] = pd.to_datetime(sales.end_date).dt.date
st.dataframe(
    sales.rename(
        columns={
            "sale_event": "Event",
            "start_date": "Start",
            "end_date": "End",
            "orders_per_day": "Orders/day",
            "baseline_orders_per_day": "Baseline/day",
            "volume_uplift": "Uplift ×",
            "approval_hours_delta": "Δ approval h",
            "delivery_days_delta": "Δ delivery days",
            "on_time_rate": "On-time",
            "on_time_rate_delta": "Δ on-time",
        }
    ).drop(columns=["approval_hours", "delivery_days"]),
    hide_index=True,
    width="stretch",
    column_config={
        "On-time": st.column_config.NumberColumn(format="percent"),
        "Δ on-time": st.column_config.NumberColumn(format="percent"),
    },
)

# --------------------------------------------------------------- data quality
with st.expander("Source feed health (data quality)"):
    dq = query(
        """
        SELECT extract_date, raw_rows, duplicate_rows_dropped, late_arriving_versions,
               late_arrival_rate, timestamp_anomalies, volume_zscore_28d
        FROM kpi.mart_data_quality_daily
        WHERE extract_date BETWEEN ? AND ?
        ORDER BY extract_date
        """,
        (start, end),
    )
    q1, q2 = st.columns(2)
    with q1:
        st.markdown("**Late-arriving CDC rows, % of daily versions**")
        fig = go.Figure(
            go.Scatter(
                x=dq.extract_date,
                y=dq.late_arrival_rate,
                mode="lines",
                line=dict(color=SERIES[0], width=2),
                hovertemplate="%{x|%d %b %Y}<br>%{y:.2%} late<extra></extra>",
            )
        )
        fig.update_yaxes(tickformat=".1%", rangemode="tozero")
        st.plotly_chart(base_layout(fig, height=260, hovermode="x"), width="stretch")
    with q2:
        st.markdown("**Duplicate rows dropped per day**")
        fig = go.Figure(
            go.Bar(
                x=dq.extract_date,
                y=dq.duplicate_rows_dropped,
                marker=dict(color=SERIES[0]),
                hovertemplate="%{x|%d %b %Y}<br>%{y} duplicates<extra></extra>",
            )
        )
        st.plotly_chart(base_layout(fig, height=260), width="stretch")
    st.dataframe(dq.tail(14).iloc[::-1], hide_index=True, width="stretch")

with st.expander("Data table: state scorecard"):
    st.dataframe(
        query("SELECT * FROM kpi.mart_state_scorecard ORDER BY on_time_rank"),
        hide_index=True,
        width="stretch",
    )
