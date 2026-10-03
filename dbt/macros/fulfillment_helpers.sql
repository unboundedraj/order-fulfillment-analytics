{# Lifecycle rank of an order status. Used to break ties between CDC versions that
   share the same updated_at timestamp (the later stage wins). #}
{% macro status_precedence(status_col) -%}
    case {{ status_col }}
        when 'created'   then 1
        when 'approved'  then 2
        when 'shipped'   then 3
        when 'delivered' then 4
        when 'cancelled' then 5
        when 'rto'       then 5
        when 'returned'  then 6
        else 0
    end
{%- endmacro %}

{# Elapsed time between two timestamps in fractional hours (null-safe). #}
{% macro hours_between(start_ts, end_ts) -%}
    (epoch({{ end_ts }}) - epoch({{ start_ts }})) / 3600.0
{%- endmacro %}

{# Elapsed time between two timestamps in fractional days (null-safe). #}
{% macro days_between(start_ts, end_ts) -%}
    (epoch({{ end_ts }}) - epoch({{ start_ts }})) / 86400.0
{%- endmacro %}

{# Extract the partition date encoded in a landing file path: orders/dt=2024-01-31/orders.csv #}
{% macro extract_date_from_path(path_col) -%}
    cast(regexp_extract({{ path_col }}, 'dt=(\d{4}-\d{2}-\d{2})', 1) as date)
{%- endmacro %}
