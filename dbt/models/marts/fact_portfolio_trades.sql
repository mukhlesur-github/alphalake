{{ config(
    materialized='incremental', unique_key='trade_id', incremental_strategy='merge',
    post_hook="delete from {{ this }} where is_cancelled"
) }}
-- Transaction fact, final state per trade. Incremental on the CDC table's updated_at; a trade cancelled
-- (or busted) after it was loaded is merged as cancelled and then removed by the post-hook.
select t.trade_id, t.trade_date, f.fund_sk, t.fund_ticker, s.security_sk, t.security_id, t.side,
       t.order_qty, t.filled_qty, t.avg_fill_price, t.fill_count, t.currency,
       t.gross_amount, t.gross_amount * fx.usd_per_unit as gross_amount_usd,
       t.commission, t.sec_fee, t.gross_amount + iff(t.side = 'BUY', 1, -1) * (t.commission + t.sec_fee) as net_amount,
       t.broker_id, t.broker_name, t.status, t.is_cancelled, t.settle_date, t.updated_at
from {{ ref('stg_trades') }} t
left join {{ ref('dim_fund') }} f
  on f.fund_ticker = t.fund_ticker and t.trade_date >= f.valid_from and t.trade_date < f.valid_to
left join {{ source('gold_tasks', 'dim_security') }} s
  on s.security_id = t.security_id and t.trade_date >= s.valid_from and t.trade_date < s.valid_to
left join (select distinct price_date, currency, usd_per_unit from {{ ref('int_prices_filled') }}) fx
  on fx.price_date = t.trade_date and fx.currency = t.currency
{% if is_incremental() %}
where t.updated_at > (select coalesce(max(updated_at), '1900-01-01'::timestamp_ltz) from {{ this }})
{% endif %}
