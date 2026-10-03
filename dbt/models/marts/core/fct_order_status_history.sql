-- Status-change fact (SCD2 grain): how long each order spent in each status.
select
    h.order_version_id,
    h.order_id,
    h.status_sequence,
    h.previous_status,
    h.order_status,
    h.valid_from,
    h.valid_to,
    h.is_current,
    h.hours_in_status,
    o.customer_state,
    o.courier,
    o.sale_event
from {{ ref('int_order_status_history') }} h
join {{ ref('fct_orders') }} o using (order_id)
