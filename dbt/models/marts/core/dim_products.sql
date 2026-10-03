select
    p.product_id,
    p.category,
    p.list_price,
    p.weight_kg,
    p.seller_id,
    s.seller_name,
    s.hub_id
from {{ ref('stg_products') }} p
left join {{ ref('stg_sellers') }} s using (seller_id)
