-- Aggregated marts must add back up to the fact table (no rows lost or double counted).
with fact as (
    select count(*) as orders, sum(gross_merchandise_value) as gmv from {{ ref('fct_orders') }}
),
daily as (
    select sum(orders) as orders, sum(gmv) as gmv from {{ ref('mart_fulfillment_daily') }}
),
scorecard as (
    select sum(orders) as orders from {{ ref('mart_state_scorecard') }}
),
funnel as (
    select sum(placed) as orders from {{ ref('mart_order_funnel') }}
)
select 'daily' as mart, d.orders, f.orders as expected from daily d, fact f
where d.orders <> f.orders or abs(d.gmv - f.gmv) > 0.01
union all
select 'scorecard', s.orders, f.orders from scorecard s, fact f where s.orders <> f.orders
union all
select 'funnel', u.orders, f.orders from funnel u, fact f where u.orders <> f.orders
