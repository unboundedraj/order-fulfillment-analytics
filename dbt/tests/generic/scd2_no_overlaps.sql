{#
  Model-level test for SCD2 tables: for each key, validity intervals must not overlap
  and must be contiguous (each version ends exactly where the next begins).
#}
{% test scd2_no_overlaps(model, key, valid_from, valid_to) %}
with ordered as (
    select
        {{ key }} as k,
        {{ valid_from }} as vf,
        {{ valid_to }} as vt,
        lead({{ valid_from }}) over (partition by {{ key }} order by {{ valid_from }}) as next_vf
    from {{ model }}
)
select *
from ordered
where vt <= vf                                  -- empty / inverted interval
   or (next_vf is not null and vt <> next_vf)   -- gap or overlap with the next version
{% endtest %}
