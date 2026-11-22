-- One price per security per trading day up to today; gaps forward-filled (and flagged).
-- FX joined and forward-filled the same way, so every row has a USD price.
with days as (
    select date_day from {{ ref('dim_date') }}
    where is_weekday and date_day between (select min(price_date) from {{ ref('stg_prices') }}) and current_date()
),
secs as (select distinct s.security_id, d.currency from {{ ref('stg_prices') }} s
         join {{ source('gold_tasks', 'dim_security') }} d on d.security_id = s.security_id and d.is_current),
grid as (select d.date_day, s.security_id, s.currency from days d cross join secs s),
filled as (
    select g.date_day as price_date, g.security_id, g.currency,
           last_value(p.close ignore nulls) over (
               partition by g.security_id order by g.date_day rows between unbounded preceding and current row) as close,
           p.close is null as is_forward_filled
    from grid g
    left join {{ ref('stg_prices') }} p on p.security_id = g.security_id and p.price_date = g.date_day
),
fx as (
    select g.date_day, c.currency,
           last_value(f.usd_per_unit ignore nulls) over (
               partition by c.currency order by g.date_day rows between unbounded preceding and current row) as usd_per_unit
    from days g
    cross join (select distinct currency from {{ ref('stg_fx') }}) c
    left join {{ ref('stg_fx') }} f on f.currency = c.currency and f.rate_date = g.date_day
)
select f.price_date, f.security_id, f.currency, f.close, fx.usd_per_unit, f.close * fx.usd_per_unit as close_usd,
       f.is_forward_filled
from filled f
join fx on fx.date_day = f.price_date and fx.currency = f.currency
where f.close is not null
