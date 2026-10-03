select
    order_id || '-' || lpad(cast(order_item_seq as varchar), 2, '0') as order_item_id,
    order_id,
    order_item_seq,
    product_id,
    seller_id,
    quantity,
    cast(unit_price as decimal(12, 2))                               as unit_price,
    cast(quantity * unit_price as decimal(14, 2))                    as line_amount,
    created_at
from {{ source('raw', 'order_items') }}
qualify row_number() over (partition by order_id, order_item_seq order by _loaded_at) = 1
