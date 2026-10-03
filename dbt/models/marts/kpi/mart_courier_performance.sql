-- Courier SLA performance by destination region and month, split by sale vs normal days.
-- Grain: month x courier x customer_region x is_sale_period.

select
    cast(date_trunc('month', order_date) as date)                          as order_month,
    courier,
    customer_region,
    sale_event is not null                                                 as is_sale_period,
    count(*) filter (where shipped_at is not null)                         as shipments,
    count(*) filter (where is_delivered)                                   as delivered,
    count(*) filter (where is_rto)                                         as rto,
    round(avg(transit_days), 2)                                            as avg_transit_days,
    round(quantile_cont(transit_days, 0.9), 2)                             as p90_transit_days,
    count(*) filter (where is_late)                                        as sla_breaches,
    round(avg(case when is_delivered then (not is_late)::int end), 4)     as on_time_rate,
    round(avg(days_late) filter (where is_late), 2)                        as avg_days_late_when_late,
    round(avg(case when shipped_at is not null then is_rto::int end), 4)   as rto_rate
from {{ ref('fct_orders') }}
where shipped_at is not null
group by all
