-- Financial reconciliation: for *settled* orders that were delivered and kept, the money
-- collected (net of refunds) must equal the basket value plus the shipping fee
-- (INR 49 below INR 499, free above).
--
-- Only orders delivered more than `settlement_days` before the newest delivery are
-- checked. Until an order is settled, a refund can legitimately land before the
-- late-arriving 'returned' status that explains it, so reconciling in-flight orders
-- would raise false alarms. Settlement = return window (12 d) + max CDC lateness (3 d)
-- + refund lag (1 d), rounded up.
{% set settlement_days = 21 %}

with cutoff as (
    select max(delivered_at) - interval {{ settlement_days }} day as settled_before
    from {{ ref('fct_orders') }}
)

select
    order_id,
    gross_merchandise_value,
    net_revenue,
    gross_merchandise_value + case when gross_merchandise_value < 499 then 49 else 0 end as expected
from {{ ref('fct_orders') }}, cutoff
where is_delivered
  and not is_returned
  and delivered_at < cutoff.settled_before
  and abs(
        net_revenue
        - (gross_merchandise_value + case when gross_merchandise_value < 499 then 49 else 0 end)
      ) > 0.01
