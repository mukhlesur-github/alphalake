-- Positions derived from executed (non-cancelled) trades: cumulative net filled quantity per trading day.
with trades_daily as (
    select fund_ticker, security_id, trade_date,
           sum(iff(side = 'BUY', 1, -1) * filled_qty) as net_qty
    from {{ ref('stg_trades') }}
    where not is_cancelled and filled_qty > 0
    group by 1, 2, 3
),
pairs as (select fund_ticker, security_id, min(trade_date) as first_date from trades_daily group by 1, 2),
grid as (
    select p.fund_ticker, p.security_id, d.date_day
    from pairs p
    join {{ ref('dim_date') }} d on d.date_day >= p.first_date and d.date_day <= current_date() and d.is_weekday
)
select g.fund_ticker, g.security_id, g.date_day as as_of_date,
       sum(coalesce(t.net_qty, 0)) over (
           partition by g.fund_ticker, g.security_id order by g.date_day rows between unbounded preceding and current row
       ) as quantity
from grid g
left join trades_daily t
  on t.fund_ticker = g.fund_ticker and t.security_id = g.security_id and t.trade_date = g.date_day
