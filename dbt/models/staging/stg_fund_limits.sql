select fund_ticker, limit_type, dimension, dimension_value, min_pct, max_pct
from {{ source('bronze', 'fund_limits_raw') }}
qualify row_number() over (partition by fund_ticker, limit_type, dimension_value order by _loaded_at desc) = 1
