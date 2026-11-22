-- fund x limit x day: actual exposure vs mandate limit (worst bucket when the limit applies to any bucket)
with h as (
    select h.as_of_date, h.fund_ticker, h.weight_pct, s.ticker, s.gics_sector, s.gics_sub_industry, s.country
    from {{ ref('fact_daily_holdings') }} h
    join {{ source('gold_tasks', 'dim_security') }} s on s.security_sk = h.security_sk
),
exposures as (
    select as_of_date, fund_ticker, 'gics_sub_industry' as dimension, gics_sub_industry as bucket, sum(weight_pct) as pct from h group by 1, 2, 3, 4
    union all
    select as_of_date, fund_ticker, 'gics_sector', gics_sector, sum(weight_pct) from h group by 1, 2, 3, 4
    union all
    select as_of_date, fund_ticker, 'country', country, sum(weight_pct) from h group by 1, 2, 3, 4
    union all
    select as_of_date, fund_ticker, 'security', ticker, sum(weight_pct) from h group by 1, 2, 3, 4
)
select e.as_of_date, e.fund_ticker, l.limit_type, l.dimension, e.bucket, round(e.pct, 4) as actual_pct,
       l.max_pct as limit_pct, e.pct > l.max_pct as is_breach, round(l.max_pct - e.pct, 4) as headroom_pct
from exposures e
join {{ ref('stg_fund_limits') }} l
  on l.fund_ticker = e.fund_ticker and l.dimension = e.dimension
 and (l.dimension_value = '*' or l.dimension_value = e.bucket)
qualify row_number() over (partition by e.as_of_date, e.fund_ticker, l.limit_type order by e.pct desc) = 1
