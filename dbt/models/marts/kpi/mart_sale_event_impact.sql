-- Operational cost of sale events: volume uplift vs the (non-sale) 28 days before each event,
-- and how much approval time, delivery time and on-time rate degrade.

with events as (

    select * from {{ ref('sale_calendar') }}

),

orders as (

    select * from {{ ref('fct_orders') }}

),

windows as (

    select
        e.sale_event,
        e.start_date,
        e.end_date,
        date_diff('day', e.start_date, e.end_date) + 1   as event_days,
        o.order_date between e.start_date and e.end_date as in_event,
        o.sale_event                                     as order_sale_event,
        o.* exclude (sale_event)
    from events e
    join orders o
        on o.order_date between e.start_date - interval 28 day and e.end_date
    -- the baseline must not contain days of an earlier sale event
    where o.order_date between e.start_date and e.end_date
        or o.sale_event is null

),

agg as (

    select
        sale_event,
        start_date,
        end_date,
        in_event,
        any_value(event_days)                                   as event_days,
        count(distinct order_date)                              as baseline_days,
        count(*)                                                as orders,
        avg(approval_hours)                                     as approval_h,
        avg(delivery_days)                                      as delivery_d,
        avg(case when is_delivered then (not is_late)::int end) as on_time
    from windows
    group by all

)

select
    e.sale_event,
    e.start_date,
    e.end_date,
    round(e.orders / e.event_days, 1)                                  as orders_per_day,
    round(b.orders / b.baseline_days, 1)                               as baseline_orders_per_day,
    round((e.orders / e.event_days) / (b.orders / b.baseline_days), 2) as volume_uplift,
    round(e.approval_h, 2)                                             as approval_hours,
    round(e.approval_h - b.approval_h, 2)                              as approval_hours_delta,
    round(e.delivery_d, 2)                                             as delivery_days,
    round(e.delivery_d - b.delivery_d, 2)                              as delivery_days_delta,
    round(e.on_time, 4)                                                as on_time_rate,
    round(e.on_time - b.on_time, 4)                                    as on_time_rate_delta
from agg e
join agg b
    on e.sale_event = b.sale_event and e.start_date = b.start_date
        and e.in_event and not b.in_event
