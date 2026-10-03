-- SCD type 2 customer dimension source: each address version is valid from its
-- updated_at until the next version (open-ended versions end at 9999-12-31 so
-- point-in-time joins can use a simple half-open interval).

with versions as (

    select * from {{ ref('stg_customers__cdc') }}

)

select
    md5(customer_id || '|' || cast(updated_at as varchar))                    as customer_sk,
    customer_id,
    state,
    state_raw,
    pincode,
    signup_at,
    updated_at                                                                as valid_from,
    coalesce(
        lead(updated_at) over (partition by customer_id order by updated_at),
        timestamp '9999-12-31 00:00:00'
    )                                                                         as valid_to,
    lead(updated_at) over (partition by customer_id order by updated_at) is null
                                                                              as is_current,
    row_number() over (partition by customer_id order by updated_at)          as version_number
from versions
