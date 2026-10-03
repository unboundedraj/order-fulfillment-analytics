-- SCD type 2 history of order status: one row per status an order has been in,
-- with the interval it was valid for. Built from the CDC log, so it is fully
-- reproducible on every run (no snapshot state to lose).

with versions as (

    select
        order_version_id,
        order_id,
        order_status,
        status_precedence,
        updated_at
    from {{ ref('stg_orders__cdc') }}

)

select
    order_version_id,
    order_id,
    order_status,
    updated_at                                                   as valid_from,
    lead(updated_at) over w                                      as valid_to,
    lead(updated_at) over w is null                              as is_current,
    lag(order_status) over w                                     as previous_status,
    {{ hours_between('updated_at', 'lead(updated_at) over w') }} as hours_in_status,
    row_number() over w                                          as status_sequence
from versions
window w as (partition by order_id order by updated_at, status_precedence)
