{{ config(alias='HOLDINGS') }}
-- Governed, flat holdings view for the app and the agent (both SQL modes target SEMANTIC.* only).
select h.as_of_date, h.fund_ticker, f.fund_name, s.ticker, s.name as security_name, s.asset_class,
       s.gics_sector, s.gics_sub_industry, s.country, h.currency, h.quantity, h.price_usd,
       h.market_value_usd, h.weight_pct
from {{ ref('fact_daily_holdings') }} h
join {{ ref('dim_fund') }} f on f.fund_sk = h.fund_sk
join {{ source('gold_tasks', 'dim_security') }} s on s.security_sk = h.security_sk
