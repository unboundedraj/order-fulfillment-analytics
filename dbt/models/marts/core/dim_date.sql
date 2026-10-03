-- Calendar dimension covering the order history plus a 60-day tail for promised dates.
-- Includes the Indian financial year (April-March) used for business reporting.

with bounds as (

    select
        cast(min(purchase_at) as date)                   as start_date,
        cast(max(purchase_at) as date) + interval 60 day as end_date
    from {{ ref('stg_orders__cdc') }}

),

days as (

    select cast(t.d as date) as date_day
    from bounds,
        range(bounds.start_date, bounds.end_date + interval 1 day, interval 1 day) as t (d)

)

select
    cast(strftime(d.date_day, '%Y%m%d') as integer) as date_key,
    d.date_day,
    year(d.date_day)                                as calendar_year,
    quarter(d.date_day)                             as calendar_quarter,
    month(d.date_day)                               as month_number,
    strftime(d.date_day, '%b')                      as month_name,
    cast(date_trunc('month', d.date_day) as date)   as month_start,
    cast(date_trunc('week', d.date_day) as date)    as week_start,
    isodow(d.date_day)                              as iso_day_of_week,
    strftime(d.date_day, '%a')                      as day_name,
    isodow(d.date_day) in (6, 7)                    as is_weekend,
    case when month(d.date_day) >= 4 then year(d.date_day) else year(d.date_day) - 1 end
        as fiscal_year_start,
    'FY' || right(cast(case when month(d.date_day) >= 4 then year(d.date_day) + 1
        else year(d.date_day)
    end as varchar), 2)                             as fiscal_year,
    s.sale_event,
    s.sale_event is not null                        as is_sale_day
from days d
left join {{ ref('sale_calendar') }} s
    on d.date_day between s.start_date and s.end_date
