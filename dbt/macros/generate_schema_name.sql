{#
  Use the configured custom schema as-is (staging, intermediate, core, kpi, reference)
  instead of dbt's default "<target_schema>_<custom_schema>" naming. Keeps warehouse
  object names stable and readable: core.fct_orders, kpi.mart_state_scorecard, ...
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
