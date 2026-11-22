{#- governance_mode (dbt var, mirrors GOVERNANCE_MODE in .env):
      policies -> table + masking / row access policies from V005 (Enterprise edition)
      views    -> secure view applying the same rules per querying role (Standard edition) -#}
{%- set by_view = var('governance_mode', 'policies') == 'views' -%}
{%- set privileged = "is_role_in_session('ALPHALAKE_PM') or is_role_in_session('ALPHALAKE_ENGINEER')" -%}
{% if by_view %}
{{ config(materialized='view', secure=true) }}
{% else %}
{{ config(post_hook=[
    "alter table {{ this }} modify column first_name set masking policy ALPHALAKE.GOLD.PII_STRING",
    "alter table {{ this }} modify column last_name set masking policy ALPHALAKE.GOLD.PII_STRING",
    "alter table {{ this }} modify column email set masking policy ALPHALAKE.GOLD.PII_STRING",
    "alter table {{ this }} modify column phone set masking policy ALPHALAKE.GOLD.PII_STRING",
    "alter table {{ this }} modify column tax_id set masking policy ALPHALAKE.GOLD.PII_STRING",
    "alter table {{ this }} add row access policy ALPHALAKE.GOLD.CLIENT_SEGMENT_RAP on (segment)",
]) }}
{% endif %}
-- SCD2 via dbt snapshot (segment / risk profile / advisor changes)
select dbt_scd_id as client_sk, client_id,
{%- for col in ['first_name', 'last_name', 'email', 'phone', 'tax_id'] %}
       {% if by_view %}case when {{ privileged }} then {{ col }} else '***MASKED***' end as {{ col }}{% else %}{{ col }}{% endif %},
{%- endfor %}
       country, state,
       segment, risk_profile, advisor_name, fund_ticker, units,
       dbt_valid_from::date as valid_from, coalesce(dbt_valid_to::date, '9999-12-31'::date) as valid_to,
       dbt_valid_to is null as is_current
from {{ ref('snap_clients') }}
{% if by_view %}where {{ privileged }} or segment <> 'Institutional'{% endif %}
