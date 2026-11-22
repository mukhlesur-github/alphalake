select rate_date, currency, usd_per_unit
from {{ source('bronze', 'fx_raw') }}
qualify row_number() over (partition by currency, rate_date order by _loaded_at desc) = 1
