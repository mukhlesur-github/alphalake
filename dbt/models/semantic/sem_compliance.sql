{{ config(alias='COMPLIANCE') }}
select as_of_date, fund_ticker, limit_type, dimension, bucket, actual_pct, limit_pct, is_breach, headroom_pct
from {{ ref('fact_compliance_checks') }}
