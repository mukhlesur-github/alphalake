-- Governance policies (attached to GOLD.DIM_CLIENT by dbt post-hooks; Enterprise) + agent audit log.
USE SCHEMA ALPHALAKE.GOLD;

{% if governance_mode == 'policies' %}
-- PII is visible only to the PM persona and engineers; everyone else sees a mask.
CREATE MASKING POLICY IF NOT EXISTS PII_STRING AS (val STRING) RETURNS STRING ->
  CASE WHEN IS_ROLE_IN_SESSION('ALPHALAKE_PM') OR IS_ROLE_IN_SESSION('ALPHALAKE_ENGINEER') THEN val
       ELSE '***MASKED***' END;

-- Analysts can't see institutional clients at all.
CREATE ROW ACCESS POLICY IF NOT EXISTS CLIENT_SEGMENT_RAP AS (segment STRING) RETURNS BOOLEAN ->
  IS_ROLE_IN_SESSION('ALPHALAKE_PM') OR IS_ROLE_IN_SESSION('ALPHALAKE_ENGINEER') OR segment <> 'Institutional';
{% else %}
-- GOVERNANCE_MODE=views (Standard edition: no masking / row access policies). The same rules live in the
-- GOLD.DIM_CLIENT secure view built by dbt (models/marts/dim_client.sql).
{% endif %}

CREATE TABLE IF NOT EXISTS ALPHALAKE.AUDIT.AGENT_INTERACTIONS (
  interaction_id STRING DEFAULT UUID_STRING(), ts TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
  role_name STRING, question STRING, mode STRING, route STRING, sql_text ARRAY, citations VARIANT,
  answer STRING, guardrail_flags ARRAY, latency_ms NUMBER, feedback STRING);

GRANT INSERT, SELECT ON TABLE ALPHALAKE.AUDIT.AGENT_INTERACTIONS TO ROLE ALPHALAKE_PM;
GRANT INSERT, SELECT ON TABLE ALPHALAKE.AUDIT.AGENT_INTERACTIONS TO ROLE ALPHALAKE_ANALYST;
