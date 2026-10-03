select
    product_id,
    category,
    cast(list_price as decimal(12, 2)) as list_price,
    weight_kg,
    seller_id
from {{ source('raw', 'products') }}
