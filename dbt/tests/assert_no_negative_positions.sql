select * from {{ ref('fact_daily_holdings') }} where quantity < 0
