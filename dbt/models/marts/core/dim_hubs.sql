select
    h.hub_id,
    h.hub_state,
    h.hub_region,
    count(s.seller_id) as seller_count
from {{ ref('ref_hubs') }} h
left join {{ ref('stg_sellers') }} s using (hub_id)
group by all
