{# `dbt run-operation create_semantic_view` -- Snowflake semantic view over the Gold star schema.
   security_sk / fund_sk on the fact are already point-in-time, so plain key relationships are correct. #}
{% macro create_semantic_view() %}
  {% set ddl %}
  CREATE OR REPLACE SEMANTIC VIEW ALPHALAKE.SEMANTIC.PORTFOLIO_ANALYTICS
    TABLES (
      holdings AS ALPHALAKE.GOLD.FACT_DAILY_HOLDINGS PRIMARY KEY (holding_id)
        COMMENT = 'Daily fund x security positions valued in USD',
      securities AS ALPHALAKE.GOLD.DIM_SECURITY PRIMARY KEY (security_sk),
      funds AS ALPHALAKE.GOLD.DIM_FUND PRIMARY KEY (fund_sk)
    )
    RELATIONSHIPS (
      holdings_to_security AS holdings (security_sk) REFERENCES securities,
      holdings_to_fund AS holdings (fund_sk) REFERENCES funds
    )
    FACTS (
      holdings.market_value_usd AS market_value_usd,
      holdings.weight_pct AS weight_pct
    )
    DIMENSIONS (
      holdings.as_of_date AS as_of_date,
      funds.fund_ticker AS fund_ticker,
      funds.fund_name AS fund_name,
      securities.ticker AS ticker,
      securities.gics_sector AS gics_sector,
      securities.gics_sub_industry AS gics_sub_industry,
      securities.country AS country
    )
    METRICS (
      holdings.total_market_value_usd AS SUM(holdings.market_value_usd),
      holdings.exposure_pct AS SUM(holdings.weight_pct)
    )
    COMMENT = 'AlphaLake governed portfolio metrics';
  {% endset %}
  {% do run_query(ddl) %}
  {% for role in ['ALPHALAKE_PM', 'ALPHALAKE_ANALYST'] %}
    {% do run_query("GRANT SELECT ON SEMANTIC VIEW ALPHALAKE.SEMANTIC.PORTFOLIO_ANALYTICS TO ROLE " ~ role) %}
  {% endfor %}
  {{ log("semantic view ALPHALAKE.SEMANTIC.PORTFOLIO_ANALYTICS created", info=True) }}
{% endmacro %}
