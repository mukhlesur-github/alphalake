-- Custodian's month-end view (independent source of truth, used for reconciliation)
select as_of_date, fund_id as fund_ticker, security_id, quantity, currency, custodian, market_value_local
from {{ source('bronze', 'holdings_raw') }}
qualify row_number() over (partition by fund_id, security_id, as_of_date order by _loaded_at desc) = 1
