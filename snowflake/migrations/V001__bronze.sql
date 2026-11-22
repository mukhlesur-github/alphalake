-- Bronze: raw landing tables, file formats, external stage (via storage integration), Snowpipes.
-- Every Bronze row carries _FILE and _LOADED_AT so any Silver/Gold row can be traced to its S3 object.
USE SCHEMA ALPHALAKE.BRONZE;

CREATE FILE FORMAT IF NOT EXISTS FF_CSV
  TYPE = CSV PARSE_HEADER = TRUE FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  EMPTY_FIELD_AS_NULL = TRUE NULL_IF = ('') ERROR_ON_COLUMN_COUNT_MISMATCH = FALSE;
CREATE FILE FORMAT IF NOT EXISTS FF_PARQUET TYPE = PARQUET;
CREATE FILE FORMAT IF NOT EXISTS FF_JSON TYPE = JSON STRIP_OUTER_ARRAY = FALSE;

-- No AWS keys: Snowflake assumes the IAM role trusted in Terraform (external ID handshake).
CREATE STAGE IF NOT EXISTS LANDING
  URL = 's3://{{bucket}}/landing/'
  STORAGE_INTEGRATION = ALPHALAKE_S3_INT;

CREATE TABLE IF NOT EXISTS SECURITIES_RAW (
  security_id STRING, ticker STRING, isin STRING, name STRING, asset_class STRING, gics_sector STRING,
  gics_sub_industry STRING, country STRING, currency STRING, credit_rating STRING, esg_score NUMBER,
  coupon FLOAT, maturity_date DATE, as_of_date DATE,
  _file STRING, _loaded_at TIMESTAMP_LTZ);

CREATE TABLE IF NOT EXISTS FUNDS_RAW (
  fund_id STRING, fund_ticker STRING, fund_name STRING, strategy STRING, region STRING, expense_ratio FLOAT,
  inception_date DATE, manager_name STRING, manager_email STRING, as_of_date DATE,
  _file STRING, _loaded_at TIMESTAMP_LTZ);

CREATE TABLE IF NOT EXISTS FUND_LIMITS_RAW (
  fund_ticker STRING, limit_type STRING, dimension STRING, dimension_value STRING, min_pct FLOAT, max_pct FLOAT,
  _file STRING, _loaded_at TIMESTAMP_LTZ);

CREATE TABLE IF NOT EXISTS CLIENTS_RAW (
  client_id STRING, first_name STRING, last_name STRING, email STRING, phone STRING, tax_id STRING,
  country STRING, state STRING, segment STRING, risk_profile STRING, advisor_name STRING, fund_ticker STRING,
  units FLOAT, as_of_date DATE,
  _file STRING, _loaded_at TIMESTAMP_LTZ);

CREATE TABLE IF NOT EXISTS PRICES_RAW (
  price_date DATE, security_id STRING, close FLOAT, volume NUMBER,
  _file STRING, _loaded_at TIMESTAMP_LTZ);

CREATE TABLE IF NOT EXISTS FX_RAW (
  rate_date DATE, currency STRING, usd_per_unit FLOAT,
  _file STRING, _loaded_at TIMESTAMP_LTZ);

CREATE TABLE IF NOT EXISTS HOLDINGS_RAW (
  as_of_date DATE, fund_id STRING, security_id STRING, quantity FLOAT, currency STRING, custodian STRING,
  market_value_local FLOAT,
  _file STRING, _loaded_at TIMESTAMP_LTZ);

-- Semi-structured: keep the whole payload as VARIANT; Silver parses it tolerantly (schema drift).
CREATE TABLE IF NOT EXISTS TRADE_EVENTS_RAW (raw VARIANT, _file STRING, _loaded_at TIMESTAMP_LTZ);
CREATE TABLE IF NOT EXISTS DOC_PARSED_RAW  (raw VARIANT, _file STRING, _loaded_at TIMESTAMP_LTZ);

-- Snowpipes (auto-ingest). All pipes in an account share one SQS queue: SHOW PIPES -> notification_channel,
-- which `make wire-snowpipe` feeds back into Terraform as the S3 bucket notification target.
{% for name, table, path, ff in [
  ("PIPE_SECURITIES",  "SECURITIES_RAW",  "batch/securities/",  "FF_CSV"),
  ("PIPE_FUNDS",       "FUNDS_RAW",       "batch/funds/",       "FF_CSV"),
  ("PIPE_FUND_LIMITS", "FUND_LIMITS_RAW", "batch/fund_limits/", "FF_CSV"),
  ("PIPE_CLIENTS",     "CLIENTS_RAW",     "batch/clients/",     "FF_CSV"),
  ("PIPE_PRICES",      "PRICES_RAW",      "batch/prices/",      "FF_PARQUET"),
  ("PIPE_FX",          "FX_RAW",          "batch/fx/",          "FF_PARQUET"),
  ("PIPE_HOLDINGS",    "HOLDINGS_RAW",    "batch/holdings/",    "FF_PARQUET")] %}
CREATE PIPE IF NOT EXISTS {{ name }} AUTO_INGEST = TRUE AS
  COPY INTO {{ table }}
  FROM @LANDING/{{ path }}
  FILE_FORMAT = (FORMAT_NAME = {{ ff }})
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  INCLUDE_METADATA = (_file = METADATA$FILENAME, _loaded_at = METADATA$START_SCAN_TIME);
{% endfor %}

CREATE PIPE IF NOT EXISTS PIPE_TRADE_EVENTS AUTO_INGEST = TRUE AS
  COPY INTO TRADE_EVENTS_RAW (raw, _file, _loaded_at)
  FROM (SELECT $1, METADATA$FILENAME, METADATA$START_SCAN_TIME FROM @LANDING/trades/)
  FILE_FORMAT = (FORMAT_NAME = FF_JSON);

CREATE PIPE IF NOT EXISTS PIPE_DOC_PARSED AUTO_INGEST = TRUE AS
  COPY INTO DOC_PARSED_RAW (raw, _file, _loaded_at)
  FROM (SELECT $1, METADATA$FILENAME, METADATA$START_SCAN_TIME FROM @LANDING/docs/parsed/)
  FILE_FORMAT = (FORMAT_NAME = FF_JSON);
