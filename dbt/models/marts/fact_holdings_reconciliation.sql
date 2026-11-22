-- Custodian (month-end files) vs trade-derived positions
with c as (select * from {{ ref('stg_holdings') }}),
d as (select * from {{ ref('int_positions_daily') }}
      where as_of_date in (select distinct as_of_date from {{ ref('stg_holdings') }}) and quantity <> 0)
select coalesce(c.as_of_date, d.as_of_date) as as_of_date,
       coalesce(c.fund_ticker, d.fund_ticker) as fund_ticker,
       coalesce(c.security_id, d.security_id) as security_id,
       c.quantity as custodian_qty, d.quantity as derived_qty,
       coalesce(c.quantity, 0) - coalesce(d.quantity, 0) as break_qty,
       abs(coalesce(c.quantity, 0) - coalesce(d.quantity, 0)) > 0.5 as is_break,
       case when c.quantity is null then 'MISSING_AT_CUSTODIAN'
            when d.quantity is null then 'MISSING_IN_BOOKS'
            when abs(c.quantity - d.quantity) > 0.5 then 'QUANTITY_MISMATCH' end as break_type
from c
full outer join d on c.fund_ticker = d.fund_ticker and c.security_id = d.security_id and c.as_of_date = d.as_of_date
