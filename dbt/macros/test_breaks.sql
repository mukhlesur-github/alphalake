{% test dbt_breaks_under_threshold(model, max_pct) %}
-- Recon breaks are expected (planted), but more than max_pct% of rows means something is broken upstream.
select count_if(is_break) * 100.0 / nullif(count(*), 0) as break_pct
from {{ model }}
having break_pct > {{ max_pct }}
{% endtest %}
