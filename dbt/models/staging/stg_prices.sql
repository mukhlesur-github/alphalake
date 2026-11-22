select price_date, security_id, close, volume
from {{ source('bronze', 'prices_raw') }}
where close > 0
qualify row_number() over (partition by security_id, price_date order by _loaded_at desc) = 1
