-- One row per state: volume, speed, reliability and how each compares to the national
-- benchmark. Answers "which states are underserved and why?"

with by_state as (

    select
        customer_state                                                      as state,
        customer_region                                                     as region,
        remoteness_tier,
        count(*)                                                            as orders,
        round(avg(approval_hours), 2)                                       as avg_approval_hours,
        round(avg(processing_hours), 2)                                     as avg_processing_hours,
        round(avg(transit_days), 2)                                         as avg_transit_days,
        round(avg(delivery_days), 2)                                        as avg_delivery_days,
        round(quantile_cont(delivery_days, 0.5), 2)                         as p50_delivery_days,
        round(quantile_cont(delivery_days, 0.9), 2)                         as p90_delivery_days,
        round(avg(case when is_delivered then (not is_late)::int end), 4)  as on_time_rate,
        round(avg(is_cancelled::int), 4)                                    as cancellation_rate,
        round(avg(is_rto::int), 4)                                          as rto_rate,
        round(avg(case when is_delivered then is_returned::int end), 4)    as return_rate,
        round(avg(is_cross_region::int), 4)                                 as cross_region_share,
        sum(gross_merchandise_value)                                        as gmv
    from {{ ref('fct_orders') }}
    group by all

),

national as (

    select
        avg(delivery_days)                                                  as nat_delivery_days,
        avg(case when is_delivered then (not is_late)::int end)            as nat_on_time_rate
    from {{ ref('fct_orders') }}

)

select
    s.*,
    round(s.avg_delivery_days - n.nat_delivery_days, 2)                     as delivery_days_vs_national,
    round(s.on_time_rate - n.nat_on_time_rate, 4)                           as on_time_rate_vs_national,
    rank() over (order by s.on_time_rate desc)                              as on_time_rank,
    rank() over (order by s.avg_delivery_days asc)                          as speed_rank,
    case
        when s.on_time_rate < n.nat_on_time_rate - 0.10 then 'critical'
        when s.on_time_rate < n.nat_on_time_rate - 0.03 then 'at risk'
        else 'healthy'
    end                                                                     as sla_health
from by_state s
cross join national n
