select
    seller_id,
    seller_name,
    hub_id,
    hub_state,
    onboarded_at
from {{ source('raw', 'sellers') }}
