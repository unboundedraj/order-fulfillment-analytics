-- SCD type 2 customer dimension. Facts reference `customer_sk`, which pins each order
-- to the customer version (address/state) that was valid when the order was placed.

select
    c.customer_sk,
    c.customer_id,
    c.state,
    g.region,
    g.remoteness_tier,
    c.state_raw,
    c.pincode,
    c.signup_at,
    c.valid_from,
    c.valid_to,
    c.is_current,
    c.version_number
from {{ ref('int_customers__scd2') }} c
left join {{ ref('dim_geography') }} g using (state)
