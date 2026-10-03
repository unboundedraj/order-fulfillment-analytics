with items as (

    select
        i.*,
        p.category
    from {{ ref('stg_order_items') }} i
    left join {{ ref('stg_products') }} p using (product_id)

)

select
    order_id,
    count(*)                                                    as item_count,
    sum(quantity)                                               as units,
    cast(sum(line_amount) as decimal(14, 2))                    as gross_merchandise_value,
    count(distinct category)                                    as distinct_categories,
    arg_max(category, line_amount)                              as primary_category,
    count(distinct seller_id)                                   as distinct_sellers
from items
group by order_id
