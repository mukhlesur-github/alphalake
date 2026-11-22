with d as (
    select dateadd(day, seq4(), '2015-01-01'::date) as date_day
    from table(generator(rowcount => 6210))
)
select date_day,
       year(date_day) as year, quarter(date_day) as quarter, month(date_day) as month,
       year(date_day) || '-Q' || quarter(date_day) as quarter_label,
       dayofweekiso(date_day) <= 5 as is_weekday,
       date_day = last_day(date_day) as is_month_end
from d
