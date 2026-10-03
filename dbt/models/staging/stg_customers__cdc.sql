-- Customer address versions with the free-text state normalised to a canonical name.
-- Unmapped spellings are kept (state = null, state_raw preserved) and caught by tests.

with source as (

    select * from {{ source('raw', 'customers') }}

),

aliases as (

    select alias, state from {{ ref('state_aliases') }}

),

deduplicated as (

    select *
    from source
    qualify row_number() over (
            partition by customer_id, updated_at order by _loaded_at desc
        ) = 1

)

select
    d.customer_id,
    d.state                     as state_raw,
    a.state                     as state,
    a.state is not null         as is_state_mapped,
    nullif(trim(d.pincode), '') as pincode,
    d.signup_at,
    d.updated_at,
    d._source_file,
    d._loaded_at
from deduplicated d
left join aliases a
    on lower(trim(d.state)) = a.alias
