-- Monthly order funnel: placed -> approved -> shipped -> delivered -> kept (not returned),
-- with stage-to-stage conversion.

select
    cast(date_trunc('month', order_date) as date)               as order_month,
    count(*)                                                    as placed,
    count(approved_at)                                          as approved,
    count(shipped_at)                                           as shipped,
    count(*) filter (where is_delivered)                        as delivered,
    count(*) filter (where is_delivered and not is_returned)    as kept,
    count(*) filter (where is_cancelled)                        as cancelled,
    count(*) filter (where is_rto)                              as returned_to_origin,
    round(count(approved_at) / count(*), 4)                     as approval_rate,
    round(count(shipped_at) / nullif(count(approved_at), 0), 4) as ship_rate,
    round(
        count(*) filter (where is_delivered)
        / nullif(count(shipped_at), 0), 4
    )                                                           as delivery_rate,
    round(
        count(*) filter (where is_delivered and not is_returned)
        / count(*), 4
    )                                                           as end_to_end_conversion
from {{ ref('fct_orders') }}
group by 1
