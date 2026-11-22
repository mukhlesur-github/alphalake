select as_of_date, fund_sk, fund_ticker, sum(market_value_usd) as net_asset_value_usd, count(*) as positions
from {{ ref('fact_daily_holdings') }}
group by 1, 2, 3
