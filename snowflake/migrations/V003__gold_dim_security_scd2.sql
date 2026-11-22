-- Hand-written SCD Type 2: BRONZE.SECURITIES_RAW (monthly full snapshots) -> GOLD.DIM_SECURITY.
-- * hash_diff over tracked attributes: unchanged rows re-sent every month create no new version
-- * snapshots applied strictly in as_of_date order; a watermark rejects late/older snapshots
-- * invalid ISINs (format check) -> quarantine
-- * re-running is a no-op (idempotency test in tests/sql/)
USE SCHEMA ALPHALAKE.GOLD;

CREATE STREAM IF NOT EXISTS ALPHALAKE.BRONZE.SECURITIES_RAW_STREAM
  ON TABLE ALPHALAKE.BRONZE.SECURITIES_RAW APPEND_ONLY = TRUE;

CREATE TRANSIENT TABLE IF NOT EXISTS ALPHALAKE.SILVER.SECURITIES_PENDING LIKE ALPHALAKE.BRONZE.SECURITIES_RAW;
-- One snapshot date at a time, with its hash_diff (transient, not TEMP: no DDL inside the transaction)
CREATE TRANSIENT TABLE IF NOT EXISTS ALPHALAKE.SILVER.SECURITIES_SNAP LIKE ALPHALAKE.BRONZE.SECURITIES_RAW;
ALTER TABLE ALPHALAKE.SILVER.SECURITIES_SNAP ADD COLUMN IF NOT EXISTS hash_diff STRING;
CREATE TABLE IF NOT EXISTS ALPHALAKE.SILVER.QUARANTINE_SECURITIES (
  security_id STRING, isin STRING, as_of_date DATE, reason STRING, _file STRING, quarantined_at TIMESTAMP_LTZ);
CREATE TABLE IF NOT EXISTS ALPHALAKE.AUDIT.SCD2_WATERMARK (entity STRING, as_of_date DATE, processed_at TIMESTAMP_LTZ,
  rows_closed NUMBER, rows_inserted NUMBER);

CREATE SEQUENCE IF NOT EXISTS SEQ_SECURITY_SK;

CREATE TABLE IF NOT EXISTS DIM_SECURITY (
  security_sk NUMBER DEFAULT SEQ_SECURITY_SK.NEXTVAL,
  security_id STRING, isin STRING, ticker STRING, name STRING, asset_class STRING,
  gics_sector STRING, gics_sub_industry STRING, country STRING, currency STRING,
  credit_rating STRING, esg_score NUMBER, coupon FLOAT, maturity_date DATE,
  hash_diff STRING, valid_from DATE, valid_to DATE, is_current BOOLEAN, _updated_at TIMESTAMP_LTZ);

CREATE OR REPLACE PROCEDURE SP_LOAD_DIM_SECURITY()
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
  watermark DATE;
  closed INT DEFAULT 0;
  inserted INT DEFAULT 0;
  dates_done INT DEFAULT 0;
  c CURSOR FOR SELECT DISTINCT as_of_date FROM ALPHALAKE.SILVER.SECURITIES_PENDING ORDER BY as_of_date;
BEGIN
  BEGIN TRANSACTION;
  INSERT INTO ALPHALAKE.SILVER.SECURITIES_PENDING
    SELECT security_id, ticker, isin, name, asset_class, gics_sector, gics_sub_industry, country, currency, credit_rating, esg_score, coupon, maturity_date, as_of_date, _file, _loaded_at
    FROM ALPHALAKE.BRONZE.SECURITIES_RAW_STREAM;

  INSERT INTO ALPHALAKE.SILVER.QUARANTINE_SECURITIES
    SELECT security_id, isin, as_of_date, 'invalid ISIN', _file, CURRENT_TIMESTAMP()
    FROM ALPHALAKE.SILVER.SECURITIES_PENDING
    WHERE NOT REGEXP_LIKE(isin, '^[A-Z]{2}[0-9]{9}[0-9]$');

  FOR r IN c DO
    LET d DATE := r.as_of_date;
    SELECT COALESCE(MAX(as_of_date), '1900-01-01'::DATE) INTO :watermark
      FROM ALPHALAKE.AUDIT.SCD2_WATERMARK WHERE entity = 'DIM_SECURITY';
    IF (d <= watermark) THEN
      -- late or replayed snapshot: never rewrite history out of order; make it visible instead
      INSERT INTO ALPHALAKE.SILVER.QUARANTINE_SECURITIES
        SELECT DISTINCT NULL, NULL, :d, 'snapshot older than SCD2 watermark (late arrival)', _file, CURRENT_TIMESTAMP()
        FROM ALPHALAKE.SILVER.SECURITIES_PENDING WHERE as_of_date = :d;
      CONTINUE;
    END IF;

    DELETE FROM ALPHALAKE.SILVER.SECURITIES_SNAP;
    INSERT INTO ALPHALAKE.SILVER.SECURITIES_SNAP
      SELECT security_id, ticker, isin, name, asset_class, gics_sector, gics_sub_industry, country, currency, credit_rating, esg_score, coupon, maturity_date, as_of_date, _file, _loaded_at, MD5(CONCAT_WS('|', COALESCE(ticker, '~'), COALESCE(name, '~'), COALESCE(gics_sector, '~'),
                 COALESCE(gics_sub_industry, '~'), COALESCE(country, '~'), COALESCE(credit_rating, '~'),
                 COALESCE(esg_score::STRING, '~'))) AS hash_diff
      FROM ALPHALAKE.SILVER.SECURITIES_PENDING
      WHERE as_of_date = :d AND REGEXP_LIKE(isin, '^[A-Z]{2}[0-9]{9}[0-9]$')
      QUALIFY ROW_NUMBER() OVER (PARTITION BY security_id ORDER BY _loaded_at DESC) = 1;

    -- close versions whose tracked attributes changed
    UPDATE ALPHALAKE.GOLD.DIM_SECURITY t
      SET valid_to = :d, is_current = FALSE, _updated_at = CURRENT_TIMESTAMP()
      FROM ALPHALAKE.SILVER.SECURITIES_SNAP s
      WHERE t.security_id = s.security_id AND t.is_current AND t.hash_diff <> s.hash_diff;
    closed := closed + SQLROWCOUNT;

    -- open new versions (changed or brand-new securities); first-ever version is valid from 1900-01-01
    INSERT INTO ALPHALAKE.GOLD.DIM_SECURITY (security_id, isin, ticker, name, asset_class, gics_sector,
        gics_sub_industry, country, currency, credit_rating, esg_score, coupon, maturity_date, hash_diff,
        valid_from, valid_to, is_current, _updated_at)
      SELECT s.security_id, s.isin, s.ticker, s.name, s.asset_class, s.gics_sector, s.gics_sub_industry,
             s.country, s.currency, s.credit_rating, s.esg_score, s.coupon, s.maturity_date, s.hash_diff,
             IFF(EXISTS (SELECT 1 FROM ALPHALAKE.GOLD.DIM_SECURITY h WHERE h.security_id = s.security_id),
                 :d, '1900-01-01'::DATE),
             '9999-12-31'::DATE, TRUE, CURRENT_TIMESTAMP()
      FROM ALPHALAKE.SILVER.SECURITIES_SNAP s
      WHERE NOT EXISTS (SELECT 1 FROM ALPHALAKE.GOLD.DIM_SECURITY t
                        WHERE t.security_id = s.security_id AND t.is_current);
    inserted := inserted + SQLROWCOUNT;

    INSERT INTO ALPHALAKE.AUDIT.SCD2_WATERMARK VALUES ('DIM_SECURITY', :d, CURRENT_TIMESTAMP(), :closed, :inserted);
    dates_done := dates_done + 1;
  END FOR;

  DELETE FROM ALPHALAKE.SILVER.SECURITIES_PENDING;
  COMMIT;
  RETURN 'snapshots=' || dates_done || ' closed=' || closed || ' inserted=' || inserted;
EXCEPTION
  WHEN OTHER THEN
    ROLLBACK;
    RAISE;
END;
$$;

CREATE OR REPLACE TASK TASK_LOAD_DIM_SECURITY
  WAREHOUSE = ALPHALAKE_WH_PIPELINE
  SCHEDULE = '2 MINUTE'
  WHEN SYSTEM$STREAM_HAS_DATA('ALPHALAKE.BRONZE.SECURITIES_RAW_STREAM')
AS
  CALL GOLD.SP_LOAD_DIM_SECURITY();

-- Left SUSPENDED on purpose: Snowpipe doesn't guarantee file order, so the initial backfill of 34 monthly
-- snapshots must be applied in one run (`make backfill` executes it once, then resumes the schedule).
