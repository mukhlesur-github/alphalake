select fund_id, fund_ticker, fund_name, strategy, region, expense_ratio, inception_date,
       manager_name, manager_email, as_of_date
from {{ source('bronze', 'funds_raw') }}
qualify row_number() over (partition by fund_id, as_of_date order by _loaded_at desc) = 1
