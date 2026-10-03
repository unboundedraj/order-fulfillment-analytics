select
    state,
    state_code,
    region,
    remoteness_tier,
    case remoteness_tier
        when 1 then 'Metro / well connected'
        when 2 then 'Standard'
        else 'Remote'
    end as remoteness_label
from {{ ref('ref_states') }}
