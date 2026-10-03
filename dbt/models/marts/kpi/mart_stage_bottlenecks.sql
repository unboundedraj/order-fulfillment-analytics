-- Where does the time go? Average hours spent in each lifecycle stage per state, each
-- stage's share of total order-to-door time, and the stage with the largest excess
-- over the national average (the state's bottleneck).

with stages as (

    select
        customer_state                          as state,
        customer_region                         as region,
        count(*)                                as delivered_orders,
        avg(approval_hours)                     as approval_h,
        avg(processing_hours)                   as processing_h,
        avg(transit_days) * 24                  as transit_h
    from {{ ref('fct_orders') }}
    where delivery_days is not null
    group by all

),

national as (

    select
        avg(approval_hours)                     as nat_approval_h,
        avg(processing_hours)                   as nat_processing_h,
        avg(transit_days) * 24                  as nat_transit_h
    from {{ ref('fct_orders') }}
    where delivery_days is not null

),

scored as (

    select
        s.*,
        s.approval_h + s.processing_h + s.transit_h         as total_h,
        s.approval_h - n.nat_approval_h                     as approval_excess_h,
        s.processing_h - n.nat_processing_h                 as processing_excess_h,
        s.transit_h - n.nat_transit_h                       as transit_excess_h
    from stages s
    cross join national n

)

select
    state,
    region,
    delivered_orders,
    round(approval_h, 2)                                    as avg_approval_hours,
    round(processing_h, 2)                                  as avg_processing_hours,
    round(transit_h, 2)                                     as avg_transit_hours,
    round(total_h / 24, 2)                                  as avg_total_days,
    round(approval_h / total_h, 4)                          as approval_share,
    round(processing_h / total_h, 4)                        as processing_share,
    round(transit_h / total_h, 4)                           as transit_share,
    round(approval_excess_h, 2)                             as approval_excess_hours,
    round(processing_excess_h, 2)                           as processing_excess_hours,
    round(transit_excess_h, 2)                              as transit_excess_hours,
    case greatest(approval_excess_h, processing_excess_h, transit_excess_h)
        when approval_excess_h   then 'approval'
        when processing_excess_h then 'warehouse processing'
        else 'last-mile transit'
    end                                                     as bottleneck_stage
from scored
