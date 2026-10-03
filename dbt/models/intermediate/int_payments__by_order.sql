select
    order_id,
    cast(sum(amount) filter (where not is_refund) as decimal(14, 2))        as amount_charged,
    cast(-coalesce(sum(amount) filter (where is_refund), 0) as decimal(14, 2)) as amount_refunded,
    cast(sum(amount) as decimal(14, 2))                                     as net_amount,
    min(paid_at) filter (where not is_refund)                               as first_charged_at,
    max(paid_at) filter (where is_refund)                                   as refunded_at,
    count(*)                                                                as payment_events
from {{ ref('stg_payments') }}
group by order_id
