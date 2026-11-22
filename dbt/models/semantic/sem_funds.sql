{{ config(alias='FUNDS') }}
select fund_ticker, fund_name, strategy, region, expense_ratio, manager_name
from {{ ref('dim_fund') }} where is_current
