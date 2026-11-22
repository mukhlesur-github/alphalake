{% snapshot snap_clients %}
{{ config(target_schema='SILVER', unique_key='client_id', strategy='check',
          check_cols=['segment', 'risk_profile', 'advisor_name', 'email', 'phone']) }}
select * from {{ ref('stg_clients') }}
{% endsnapshot %}
