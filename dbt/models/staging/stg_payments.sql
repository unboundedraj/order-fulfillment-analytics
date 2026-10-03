select
    payment_id,
    order_id,
    payment_type,
    payment_method,
    cast(amount as decimal(14, 2)) as amount,
    payment_type = 'refund'        as is_refund,
    created_at                     as paid_at
from {{ source('raw', 'payments') }}
qualify row_number() over (partition by payment_id order by _loaded_at) = 1
