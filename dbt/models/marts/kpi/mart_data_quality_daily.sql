-- Source-feed observability: what the CDC extract looked like each day.
-- Tracks volume, re-sent duplicates, late arrivals and timestamp anomalies so feed
-- regressions are visible in the same dashboard as the business KPIs.

with raw_rows as (

    select
        {{ extract_date_from_path('_source_file') }}       as extract_date,
        count(*)                                           as raw_rows
    from {{ source('raw', 'orders') }}
    group by 1

),

versions as (

    select
        extract_date,
        count(*)                                           as distinct_versions,
        sum(duplicate_copies_dropped)                      as duplicate_rows_dropped,
        count(*) filter (where is_late_arrival)            as late_arriving_versions,
        max(date_diff('day', cast(updated_at as date), extract_date)) as max_arrival_lag_days
    from {{ ref('stg_orders__cdc') }}
    group by 1

),

anomalies as (

    select cast(delivered_at as date) as extract_date, count(*) as timestamp_anomalies
    from {{ ref('fct_orders') }}
    where has_timestamp_anomaly
    group by 1

)

select
    r.extract_date,
    r.raw_rows,
    v.distinct_versions,
    coalesce(v.duplicate_rows_dropped, 0)                  as duplicate_rows_dropped,
    coalesce(v.late_arriving_versions, 0)                  as late_arriving_versions,
    round(coalesce(v.late_arriving_versions, 0) / v.distinct_versions, 4) as late_arrival_rate,
    coalesce(v.max_arrival_lag_days, 0)                    as max_arrival_lag_days,
    coalesce(a.timestamp_anomalies, 0)                     as timestamp_anomalies,
    -- volume z-score vs trailing 28 days: flags sudden drops/spikes in the feed
    round(
        (r.raw_rows - avg(r.raw_rows) over w)
        / nullif(stddev_samp(r.raw_rows) over w, 0), 2
    )                                                      as volume_zscore_28d
from raw_rows r
left join versions v using (extract_date)
left join anomalies a using (extract_date)
window w as (order by r.extract_date rows between 28 preceding and 1 preceding)
