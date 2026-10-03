-- One row per *distinct* order version.
--   * exact duplicates re-sent by the extractor are removed
--   * late arrivals (row landed in a later file than the change happened) are flagged
--   * a deterministic version key makes every version addressable

with source as (

    select * from {{ source('raw', 'orders') }}

),

typed as (

    select
        order_id,
        customer_id,
        hub_id,
        courier,
        payment_method,
        order_status,
        purchase_at,
        approved_at,
        shipped_at,
        delivered_at,
        closed_at,
        estimated_delivery_date,
        updated_at,
        {{ extract_date_from_path('_source_file') }} as extract_date,
        _source_file,
        _loaded_at
    from source

),

deduplicated as (

    select
        *,
        row_number() over (
            partition by order_id, order_status, updated_at
            order by _loaded_at, _source_file
        )                                                               as _dup_rank,
        count(*) over (partition by order_id, order_status, updated_at) as _copies_received
    from typed

)

select
    md5(order_id || '|' || order_status || '|' || cast(updated_at as varchar)) as order_version_id,
    order_id,
    customer_id,
    hub_id,
    courier,
    payment_method,
    order_status,
    {{ status_precedence('order_status') }}                                    as status_precedence,
    purchase_at,
    approved_at,
    shipped_at,
    delivered_at,
    closed_at,
    estimated_delivery_date,
    updated_at,
    extract_date,
    extract_date > cast(updated_at as date)                                    as is_late_arrival,
    _copies_received - 1                                                       as duplicate_copies_dropped,
    _source_file,
    _loaded_at
from deduplicated
where _dup_rank = 1
