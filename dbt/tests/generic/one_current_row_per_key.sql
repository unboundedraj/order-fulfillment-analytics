{% test one_current_row_per_key(model, key, current_flag='is_current') %}
-- Every key in an SCD2 table must have exactly one current version.
select {{ key }}, count(*) filter (where {{ current_flag }}) as current_rows
from {{ model }}
group by {{ key }}
having count(*) filter (where {{ current_flag }}) <> 1
{% endtest %}
