{{ config(alias='TRADES') }}
select t.trade_date, t.fund_ticker, s.ticker, s.name as security_name, t.side, t.filled_qty, t.avg_fill_price,
       t.gross_amount_usd, t.broker_name, t.status
from {{ ref('fact_portfolio_trades') }} t
left join {{ source('gold_tasks', 'dim_security') }} s on s.security_sk = t.security_sk
