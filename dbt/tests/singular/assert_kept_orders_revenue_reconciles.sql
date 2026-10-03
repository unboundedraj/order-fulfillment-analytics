-- Financial reconciliation: for orders that were delivered and kept, the money collected
-- (net of refunds) must equal the basket value plus the shipping fee
-- (INR 49 below INR 499, free above).
select
    order_id,
    gross_merchandise_value,
    net_revenue,
    gross_merchandise_value + case when gross_merchandise_value < 499 then 49 else 0 end as expected
from {{ ref('fct_orders') }}
where is_delivered
  and not is_returned
  and abs(
        net_revenue
        - (gross_merchandise_value + case when gross_merchandise_value < 499 then 49 else 0 end)
      ) > 0.01
