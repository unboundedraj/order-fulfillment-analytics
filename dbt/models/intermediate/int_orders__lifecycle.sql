-- One row per order with every lifecycle timestamp, stage durations, SLA outcomes
-- and the customer's location *as it was when the order was placed* (point-in-time
-- join against the SCD2 customer history).

with orders as (

    select * from {{ ref('int_orders__latest') }}

),

customers as (

    select * from {{ ref('int_customers__scd2') }}

),

states as (

    select * from {{ ref('ref_states') }}

),

hubs as (

    select * from {{ ref('ref_hubs') }}

),

sales as (

    select * from {{ ref('sale_calendar') }}

),

as_of as (

    -- "now" for the dataset: the newest event we have seen
    select max(updated_at) as as_of_ts from {{ ref('stg_orders__cdc') }}

),

joined as (

    select
        o.order_id,
        o.customer_id,
        c.customer_sk,
        c.state        as customer_state,
        s.region       as customer_region,
        s.remoteness_tier,
        o.hub_id,
        h.hub_state,
        h.hub_region,
        o.courier,
        o.payment_method,
        o.order_status as current_status,
        o.purchase_at,
        o.approved_at,
        o.shipped_at,
        o.delivered_at,
        o.closed_at,
        o.estimated_delivery_date,
        o.updated_at   as last_status_change_at,
        o.version_count,
        o.had_late_arrival,
        sc.sale_event,
        greatest(o.last_loaded_at, coalesce(p.last_payment_loaded_at, o.last_loaded_at))
            as source_last_loaded_at,
        a.as_of_ts
    from orders o
    cross join as_of a
    left join customers c
        on o.customer_id = c.customer_id
            and o.purchase_at >= c.valid_from
            and o.purchase_at < c.valid_to
    left join states s on c.state = s.state
    left join hubs h on o.hub_id = h.hub_id
    left join sales sc
        on cast(o.purchase_at as date) between sc.start_date and sc.end_date
    left join (
        select order_id, max(_loaded_at) as last_payment_loaded_at
        from {{ source('raw', 'payments') }}
        group by order_id
    ) p on o.order_id = p.order_id

)

-- Alias alignment can't be checked here: macro expansions change line lengths.
-- noqa: disable=LT01
select
    *,
    delivered_at is not null and delivered_at < shipped_at             as has_timestamp_anomaly,
    current_status in ('delivered', 'returned')                        as is_delivered,
    current_status = 'cancelled'                                       as is_cancelled,
    current_status = 'returned'                                        as is_returned,
    current_status = 'rto'                                             as is_rto,
    current_status in ('created', 'approved', 'shipped')               as is_open,
    customer_region <> hub_region                                      as is_cross_region,

    {{ hours_between('purchase_at', 'approved_at') }}                  as approval_hours,
    {{ hours_between('approved_at', 'shipped_at') }}                   as processing_hours,
    case when delivered_at >= shipped_at
            then {{ days_between('shipped_at', 'delivered_at') }}
    end     as transit_days,
    case when delivered_at >= shipped_at
            then {{ days_between('purchase_at', 'delivered_at') }}
    end    as delivery_days,

    case when delivered_at is not null
            then cast(delivered_at as date) > estimated_delivery_date
    end as is_late,
    case when delivered_at is not null
            then greatest(date_diff('day', estimated_delivery_date, cast(delivered_at as date)), 0)
    end                                                                as days_late,
    current_status in ('created', 'approved', 'shipped')
    and cast(as_of_ts as date) > estimated_delivery_date           as is_open_and_overdue,
    {{ hours_between('purchase_at', 'approved_at') }} > {{ var('approval_sla_hours') }}
        as breached_approval_sla
from joined
-- noqa: enable=LT01
