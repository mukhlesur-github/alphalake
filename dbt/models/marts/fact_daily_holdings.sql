-- Periodic snapshot: fund x security x trading day. Point-in-time joins: the security attributes
-- (sector, sub-industry) are the ones valid ON as_of_date, via the SCD2 interval.
with pos as (select * from {{ ref('int_positions_daily') }} where quantity <> 0),
valued as (
    select p.as_of_date, p.fund_ticker, p.security_id, p.quantity, px.currency, px.close as price_local,
           px.close_usd as price_usd, p.quantity * px.close_usd as market_value_usd, px.is_forward_filled
    from pos p
    join {{ ref('int_prices_filled') }} px on px.security_id = p.security_id and px.price_date = p.as_of_date
)
select md5(v.fund_ticker || '|' || v.security_id || '|' || v.as_of_date) as holding_id,
       v.as_of_date, f.fund_sk, v.fund_ticker, s.security_sk, v.security_id, v.quantity, v.currency,
       v.price_local, v.price_usd, v.market_value_usd,
       100 * v.market_value_usd / sum(v.market_value_usd) over (partition by v.fund_ticker, v.as_of_date) as weight_pct,
       v.is_forward_filled
from valued v
join {{ ref('dim_fund') }} f
  on f.fund_ticker = v.fund_ticker and v.as_of_date >= f.valid_from and v.as_of_date < f.valid_to
join {{ source('gold_tasks', 'dim_security') }} s
  on s.security_id = v.security_id and v.as_of_date >= s.valid_from and v.as_of_date < s.valid_to
