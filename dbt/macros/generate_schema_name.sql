{# Use the configured schema verbatim (SILVER/GOLD/SEMANTIC) instead of dbt's <target>_<custom> default. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
  {{ (custom_schema_name or target.schema) | trim | upper }}
{%- endmacro %}
