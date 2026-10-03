select
    i.order_item_id,
    i.order_id,
    i.order_item_seq,
    o.order_date_key,
    o.customer_sk,
    i.product_id,
    p.category,
    i.seller_id,
    p.hub_id,
    i.quantity,
    i.unit_price,
    i.line_amount,
    o.current_status,
    o.is_returned
from {{ ref('stg_order_items') }} i
join {{ ref('fct_orders') }} o using (order_id)
left join {{ ref('dim_products') }} p using (product_id)
