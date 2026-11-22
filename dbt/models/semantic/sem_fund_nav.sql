{{ config(alias='FUND_NAV') }}
select n.as_of_date, n.fund_ticker, f.fund_name, f.strategy, f.region, f.manager_name,
       n.net_asset_value_usd, n.positions
from {{ ref('fact_fund_nav_daily') }} n
join {{ ref('dim_fund') }} f on f.fund_sk = n.fund_sk
