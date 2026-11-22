-- Streaming CDC: BRONZE.TRADE_EVENTS_RAW --(stream)--> task --> SILVER.TRADE_EVENTS / TRADE_FILLS / TRADES_CURRENT
-- Handles: duplicates (at-least-once), out-of-order events, corrections, cancels/busts, malformed payloads,
-- schema drift (v1.0 has no fees.sec_fee).
USE SCHEMA ALPHALAKE.SILVER;

CREATE STREAM IF NOT EXISTS ALPHALAKE.BRONZE.TRADE_EVENTS_RAW_STREAM
  ON TABLE ALPHALAKE.BRONZE.TRADE_EVENTS_RAW APPEND_ONLY = TRUE;

CREATE TRANSIENT TABLE IF NOT EXISTS TRADE_EVENTS_BATCH (raw VARIANT, _file STRING, _loaded_at TIMESTAMP_LTZ);

CREATE TABLE IF NOT EXISTS QUARANTINE_TRADE_EVENTS (
  raw VARIANT, reason STRING, _file STRING, quarantined_at TIMESTAMP_LTZ);

CREATE TABLE IF NOT EXISTS TRADE_EVENTS (
  event_id STRING, event_type STRING, event_seq NUMBER, event_ts TIMESTAMP_NTZ,
  trade_id STRING, fund_id STRING, security_id STRING, side STRING, order_qty FLOAT, limit_price FLOAT,
  currency STRING, broker_id STRING, broker_name STRING, trade_date DATE,
  commission FLOAT, sec_fee FLOAT, settle_date DATE, schema_version STRING, fills VARIANT,
  _file STRING, _loaded_at TIMESTAMP_LTZ);

-- Work table for the latest event per touched trade (transient table, not TEMP: DDL inside the
-- procedure's explicit transaction would implicitly commit it).
CREATE TRANSIENT TABLE IF NOT EXISTS TRADES_TOUCHED LIKE TRADE_EVENTS;

CREATE TABLE IF NOT EXISTS TRADE_FILLS (
  trade_id STRING, fill_id STRING, qty FLOAT, price FLOAT, venue STRING, fill_ts TIMESTAMP_NTZ);

CREATE TABLE IF NOT EXISTS TRADES_CURRENT (
  trade_id STRING, fund_id STRING, security_id STRING, side STRING, order_qty FLOAT,
  filled_qty FLOAT, avg_fill_price FLOAT, fill_count NUMBER, gross_amount FLOAT, commission FLOAT, sec_fee FLOAT,
  currency STRING, broker_id STRING, broker_name STRING, trade_date DATE, settle_date DATE,
  status STRING, is_cancelled BOOLEAN, last_event_seq NUMBER, last_event_ts TIMESTAMP_NTZ, updated_at TIMESTAMP_LTZ);

CREATE OR REPLACE PROCEDURE SP_PROCESS_TRADE_EVENTS()
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
  n_batch INT; n_bad INT; n_new INT;
BEGIN
  BEGIN TRANSACTION;
  -- 1. Consume the stream (a DML read advances its offset when the transaction commits)
  DELETE FROM ALPHALAKE.SILVER.TRADE_EVENTS_BATCH;
  INSERT INTO ALPHALAKE.SILVER.TRADE_EVENTS_BATCH
    SELECT raw, _file, _loaded_at FROM ALPHALAKE.BRONZE.TRADE_EVENTS_RAW_STREAM;
  n_batch := SQLROWCOUNT;

  -- 2. Schema checks -> quarantine
  INSERT INTO ALPHALAKE.SILVER.QUARANTINE_TRADE_EVENTS
    SELECT raw,
      CASE WHEN raw:event_id IS NULL THEN 'missing event_id'
           WHEN raw:trade:trade_id IS NULL THEN 'missing trade_id'
           WHEN TRY_TO_DOUBLE(raw:trade:order_qty::STRING) IS NULL THEN 'order_qty not numeric'
           WHEN TRY_TO_NUMBER(raw:event_seq::STRING) IS NULL THEN 'event_seq not numeric'
      END, _file, CURRENT_TIMESTAMP()
    FROM ALPHALAKE.SILVER.TRADE_EVENTS_BATCH
    WHERE raw:event_id IS NULL OR raw:trade:trade_id IS NULL
       OR TRY_TO_DOUBLE(raw:trade:order_qty::STRING) IS NULL OR TRY_TO_NUMBER(raw:event_seq::STRING) IS NULL;
  n_bad := SQLROWCOUNT;

  -- 3. Valid events, deduplicated within the batch AND against history (idempotent on event_id)
  MERGE INTO ALPHALAKE.SILVER.TRADE_EVENTS t
  USING (
    SELECT raw:event_id::STRING event_id, raw:event_type::STRING event_type, raw:event_seq::NUMBER event_seq,
           raw:event_ts::TIMESTAMP_NTZ event_ts, raw:trade:trade_id::STRING trade_id, raw:trade:fund_id::STRING fund_id,
           raw:trade:security:security_id::STRING security_id, raw:trade:side::STRING side,
           raw:trade:order_qty::FLOAT order_qty, raw:trade:limit_price::FLOAT limit_price,
           raw:trade:currency::STRING currency, raw:trade:broker:broker_id::STRING broker_id,
           raw:trade:broker:name::STRING broker_name, raw:trade:trade_date::DATE trade_date,
           raw:fees:commission::FLOAT commission,
           raw:fees:sec_fee::FLOAT sec_fee,                       -- NULL for schema 1.0 (drift-tolerant)
           raw:settlement:settle_date::DATE settle_date, raw:schema_version::STRING schema_version,
           raw:fills fills, _file, _loaded_at
    FROM ALPHALAKE.SILVER.TRADE_EVENTS_BATCH
    WHERE raw:event_id IS NOT NULL AND raw:trade:trade_id IS NOT NULL
      AND TRY_TO_DOUBLE(raw:trade:order_qty::STRING) IS NOT NULL AND TRY_TO_NUMBER(raw:event_seq::STRING) IS NOT NULL
    QUALIFY ROW_NUMBER() OVER (PARTITION BY raw:event_id::STRING ORDER BY _loaded_at) = 1
  ) s ON t.event_id = s.event_id
  WHEN NOT MATCHED THEN INSERT VALUES (
    s.event_id, s.event_type, s.event_seq, s.event_ts, s.trade_id, s.fund_id, s.security_id, s.side, s.order_qty,
    s.limit_price, s.currency, s.broker_id, s.broker_name, s.trade_date, s.commission, s.sec_fee, s.settle_date,
    s.schema_version, s.fills, s._file, s._loaded_at);
  n_new := SQLROWCOUNT;

  -- 4. Recompute current state of every touched trade from its full event history:
  --    the highest event_seq wins, so out-of-order arrival can't regress state.
  DELETE FROM ALPHALAKE.SILVER.TRADES_TOUCHED;
  INSERT INTO ALPHALAKE.SILVER.TRADES_TOUCHED
    SELECT e.* FROM ALPHALAKE.SILVER.TRADE_EVENTS e
    WHERE e.trade_id IN (SELECT DISTINCT raw:trade:trade_id::STRING FROM ALPHALAKE.SILVER.TRADE_EVENTS_BATCH)
    QUALIFY ROW_NUMBER() OVER (PARTITION BY e.trade_id ORDER BY e.event_seq DESC) = 1;

  MERGE INTO ALPHALAKE.SILVER.TRADES_CURRENT t
  USING (
    SELECT l.trade_id, ANY_VALUE(l.fund_id) fund_id, ANY_VALUE(l.security_id) security_id, ANY_VALUE(l.side) side,
           ANY_VALUE(l.order_qty) order_qty, COALESCE(SUM(f.value:qty::FLOAT), 0) filled_qty,
           SUM(f.value:qty::FLOAT * f.value:price::FLOAT) / NULLIF(SUM(f.value:qty::FLOAT), 0) avg_fill_price,
           COUNT(f.value) fill_count, COALESCE(SUM(f.value:qty::FLOAT * f.value:price::FLOAT), 0) gross_amount,
           ANY_VALUE(l.commission) commission, ANY_VALUE(l.sec_fee) sec_fee, ANY_VALUE(l.currency) currency,
           ANY_VALUE(l.broker_id) broker_id, ANY_VALUE(l.broker_name) broker_name, ANY_VALUE(l.trade_date) trade_date,
           ANY_VALUE(l.settle_date) settle_date, ANY_VALUE(l.event_type) status,
           ANY_VALUE(l.event_type) = 'CANCELLED' is_cancelled, ANY_VALUE(l.event_seq) last_event_seq,
           ANY_VALUE(l.event_ts) last_event_ts
    FROM ALPHALAKE.SILVER.TRADES_TOUCHED l, LATERAL FLATTEN(input => l.fills, OUTER => TRUE) f
    GROUP BY l.trade_id
  ) s ON t.trade_id = s.trade_id
  WHEN MATCHED AND s.last_event_seq > t.last_event_seq THEN UPDATE SET
    filled_qty = s.filled_qty, avg_fill_price = s.avg_fill_price, fill_count = s.fill_count,
    gross_amount = s.gross_amount, commission = s.commission, sec_fee = s.sec_fee, settle_date = s.settle_date,
    status = s.status, is_cancelled = s.is_cancelled, last_event_seq = s.last_event_seq,
    last_event_ts = s.last_event_ts, updated_at = CURRENT_TIMESTAMP()
  WHEN NOT MATCHED THEN INSERT VALUES (
    s.trade_id, s.fund_id, s.security_id, s.side, s.order_qty, s.filled_qty, s.avg_fill_price, s.fill_count,
    s.gross_amount, s.commission, s.sec_fee, s.currency, s.broker_id, s.broker_name, s.trade_date, s.settle_date,
    s.status, s.is_cancelled, s.last_event_seq, s.last_event_ts, CURRENT_TIMESTAMP());

  -- 5. Fills of touched trades (one row per fill, from the winning event)
  DELETE FROM ALPHALAKE.SILVER.TRADE_FILLS WHERE trade_id IN (SELECT trade_id FROM ALPHALAKE.SILVER.TRADES_TOUCHED);
  INSERT INTO ALPHALAKE.SILVER.TRADE_FILLS
    SELECT l.trade_id, f.value:fill_id::STRING, f.value:qty::FLOAT, f.value:price::FLOAT,
           f.value:venue::STRING, f.value:ts::TIMESTAMP_NTZ
    FROM ALPHALAKE.SILVER.TRADES_TOUCHED l, LATERAL FLATTEN(input => l.fills) f;

  COMMIT;
  RETURN 'batch=' || n_batch || ' quarantined=' || n_bad || ' new_events=' || n_new;
EXCEPTION
  WHEN OTHER THEN
    ROLLBACK;
    RAISE;
END;
$$;

CREATE OR REPLACE TASK TASK_PROCESS_TRADE_EVENTS
  WAREHOUSE = ALPHALAKE_WH_PIPELINE
  SCHEDULE = '1 MINUTE'
  WHEN SYSTEM$STREAM_HAS_DATA('ALPHALAKE.BRONZE.TRADE_EVENTS_RAW_STREAM')  -- no warehouse spin-up when idle
AS
  CALL SILVER.SP_PROCESS_TRADE_EVENTS();

ALTER TASK TASK_PROCESS_TRADE_EVENTS RESUME;
