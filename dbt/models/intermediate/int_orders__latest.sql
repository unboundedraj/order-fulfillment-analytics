-- Current state of every order: the latest CDC version by *event time*, not arrival time.
-- Late-arriving rows therefore can never overwrite a newer status.

with versions as (

    select
        *,
        count(*) over (partition by order_id)                 as version_count,
        max(_loaded_at) over (partition by order_id)          as last_loaded_at,
        bool_or(is_late_arrival) over (partition by order_id) as had_late_arrival
    from {{ ref('stg_orders__cdc') }}

)

select *
from versions
qualify row_number() over (
        partition by order_id
        order by updated_at desc, status_precedence desc
    ) = 1
