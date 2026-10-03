{{
    config(
        materialized = 'incremental',
        unique_key = 'order_id',
        incremental_strategy = 'delete+insert',
        on_schema_change = 'fail',
        contract = {'enforced': true}
    )
}}

-- Order-grain fact table (one row per order, current state).
--
-- Incremental strategy: re-process every order that received *any* new source row
-- (order version or payment) since the last run, based on load time rather than event
-- time. Late-arriving CDC rows therefore always update their order, however old it is.

with lifecycle as (

    select * from {{ ref('int_orders__lifecycle') }}
    {% if is_incremental() %}
        where source_last_loaded_at > (select coalesce(max(source_last_loaded_at), timestamp '1900-01-01') from {{ this }})
    {% endif %}

),

items as (

    select * from {{ ref('int_order_items__by_order') }}

),

payments as (

    select * from {{ ref('int_payments__by_order') }}

)

select
    l.order_id,
    l.customer_sk,
    l.customer_id,
    cast(strftime(l.purchase_at, '%Y%m%d') as integer) as order_date_key,
    cast(l.purchase_at as date)                        as order_date,
    l.customer_state,
    l.customer_region,
    l.remoteness_tier,
    l.hub_id,
    l.hub_region,
    l.courier,
    l.payment_method,
    l.sale_event,
    l.current_status,
    l.purchase_at,
    l.approved_at,
    l.shipped_at,
    l.delivered_at,
    l.closed_at,
    l.estimated_delivery_date,
    l.is_delivered,
    l.is_cancelled,
    l.is_returned,
    l.is_rto,
    l.is_open,
    l.is_cross_region,
    l.is_late,
    l.days_late,
    l.is_open_and_overdue,
    l.breached_approval_sla,
    l.has_timestamp_anomaly,
    cast(l.approval_hours as double)                   as approval_hours,
    cast(l.processing_hours as double)                 as processing_hours,
    cast(l.transit_days as double)                     as transit_days,
    cast(l.delivery_days as double)                    as delivery_days,
    i.item_count,
    cast(i.units as bigint)                            as units,
    i.primary_category,
    i.gross_merchandise_value,
    coalesce(p.amount_charged, 0)                      as amount_charged,
    coalesce(p.amount_refunded, 0)                     as amount_refunded,
    coalesce(p.net_amount, 0)                          as net_revenue,
    l.version_count,
    l.had_late_arrival,
    l.source_last_loaded_at
from lifecycle l
left join items i using (order_id)
left join payments p using (order_id)
