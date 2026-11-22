select client_id, first_name, last_name, email, phone, tax_id, country, state, segment, risk_profile,
       advisor_name, fund_ticker, units, as_of_date
from {{ source('bronze', 'clients_raw') }}
qualify row_number() over (partition by client_id order by as_of_date desc, _loaded_at desc) = 1
