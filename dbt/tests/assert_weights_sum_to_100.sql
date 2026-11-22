select fund_ticker, as_of_date, sum(weight_pct) as total
from {{ ref('fact_daily_holdings') }}
group by 1, 2
having abs(sum(weight_pct) - 100) > 0.01
