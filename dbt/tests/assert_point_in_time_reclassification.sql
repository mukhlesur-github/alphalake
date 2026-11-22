-- The planted reclassification (equipment -> Semiconductors on 2026-06-30) must NOT rewrite history:
-- the same GTIF holding is 'Semiconductor Materials & Equipment' on 2026-05-29 and 'Semiconductors' on 2026-06-30.
with reclassed as (
    select security_id from {{ source('gold_tasks', 'dim_security') }}
    where valid_from = '2026-06-30' and gics_sub_industry = 'Semiconductors'
),
seen as (
    select h.as_of_date, s.gics_sub_industry
    from {{ ref('fact_daily_holdings') }} h
    join {{ source('gold_tasks', 'dim_security') }} s on s.security_sk = h.security_sk
    where h.fund_ticker = 'GTIF' and h.security_id in (select security_id from reclassed)
      and h.as_of_date in ('2026-05-29', '2026-06-30')
)
select * from seen
where (as_of_date = '2026-05-29' and gics_sub_industry <> 'Semiconductor Materials & Equipment')
   or (as_of_date = '2026-06-30' and gics_sub_industry <> 'Semiconductors')
union all
select null, 'reclassification not found' where (select count(*) from reclassed) = 0
