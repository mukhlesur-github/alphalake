select f.trade_id
from {{ ref('fact_portfolio_trades') }} f
join {{ source('silver_tasks', 'trades_current') }} t on t.trade_id = f.trade_id
where t.is_cancelled
