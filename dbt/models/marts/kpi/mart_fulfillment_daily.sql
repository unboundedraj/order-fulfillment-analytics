-- Daily fulfilment KPIs by customer state. Grain: order_date x customer_state.

select
    order_date,
    customer_state,
    customer_region,
    any_value(sale_event)                                                as sale_event,
    count(*)                                                             as orders,
    count(*) filter (where is_delivered)                                 as delivered_orders,
    count(*) filter (where is_cancelled)                                 as cancelled_orders,
    count(*) filter (where is_rto)                                       as rto_orders,
    count(*) filter (where is_returned)                                  as returned_orders,
    count(*) filter (where is_late)                                      as late_deliveries,
    round(avg(approval_hours), 2)                                        as avg_approval_hours,
    round(avg(processing_hours), 2)                                      as avg_processing_hours,
    round(avg(delivery_days), 2)                                         as avg_delivery_days,
    round(quantile_cont(delivery_days, 0.9), 2)                          as p90_delivery_days,
    round(count(*) filter (where is_delivered and not is_late)
          / nullif(count(*) filter (where is_delivered), 0), 4)          as on_time_rate,
    sum(gross_merchandise_value)                                         as gmv,
    sum(net_revenue)                                                     as net_revenue
from {{ ref('fct_orders') }}
group by order_date, customer_state, customer_region
