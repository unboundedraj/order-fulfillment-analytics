{#
  Asserts `column_name` is not earlier than `after` whenever both are present.
  Use `config: where:` to exclude rows that are already quarantined/flagged.
#}
{% test timestamps_in_order(model, column_name, after) %}
select *
from {{ model }}
where {{ column_name }} is not null
  and {{ after }} is not null
  and {{ column_name }} < {{ after }}
{% endtest %}
