-- Current state of every trade, maintained by the Stream + Task CDC graph (V002)
select trade_id, fund_id as fund_ticker, security_id, side, order_qty, filled_qty, avg_fill_price, fill_count,
       gross_amount, commission, coalesce(sec_fee, 0) as sec_fee, currency, broker_id, broker_name,
       trade_date, settle_date, status, is_cancelled, last_event_ts, updated_at
from {{ source('silver_tasks', 'trades_current') }}
