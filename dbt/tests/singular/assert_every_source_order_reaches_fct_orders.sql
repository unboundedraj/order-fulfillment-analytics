-- Completeness: every order that ever appeared in the raw CDC feed must exist in the fact.
select order_id from {{ source('raw', 'orders') }}
except
select order_id from {{ ref('fct_orders') }}
