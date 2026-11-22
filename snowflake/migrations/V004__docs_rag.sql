-- Unstructured pipeline: parsed-doc JSON (Snowpipe) -> stream -> task:
--   newer version of a doc_id?  delete ALL its old chunks, insert new chunks + Cortex embeddings,
--   upsert DOCS.DOCUMENTS -- in one transaction, so search never sees a half-replaced document.
USE SCHEMA ALPHALAKE.DOCS;

CREATE STREAM IF NOT EXISTS ALPHALAKE.BRONZE.DOC_PARSED_RAW_STREAM
  ON TABLE ALPHALAKE.BRONZE.DOC_PARSED_RAW APPEND_ONLY = TRUE;

CREATE TRANSIENT TABLE IF NOT EXISTS DOC_PENDING (raw VARIANT, _loaded_at TIMESTAMP_LTZ);

CREATE TABLE IF NOT EXISTS DOCUMENTS (
  doc_id STRING, version NUMBER, sha256 STRING, title STRING, doc_type STRING, fund_ticker STRING,
  access_tier STRING, publish_date DATE, source_uri STRING, chunk_count NUMBER, pii_redactions NUMBER,
  updated_at TIMESTAMP_LTZ);

CREATE TABLE IF NOT EXISTS DOC_CHUNKS (
  chunk_id STRING, doc_id STRING, version NUMBER, chunk_index NUMBER, chunk_type STRING, section_title STRING,
  page_number NUMBER, chunk_text STRING, title STRING, doc_type STRING, fund_ticker STRING, access_tier STRING,
  publish_date DATE, embedding VECTOR(FLOAT, 1024), embedding_model STRING);

-- Latest pending version per doc that is genuinely new (higher version AND different content hash)
CREATE OR REPLACE VIEW V_DOC_UPDATES AS
  SELECT p.*
  FROM (SELECT raw:doc_id::STRING doc_id, raw:version::NUMBER version, raw:sha256::STRING sha256, raw
        FROM DOC_PENDING
        QUALIFY ROW_NUMBER() OVER (PARTITION BY raw:doc_id::STRING ORDER BY raw:version::NUMBER DESC) = 1) p
  LEFT JOIN DOCUMENTS d ON d.doc_id = p.doc_id
  WHERE p.version > COALESCE(d.version, 0) AND (d.sha256 IS NULL OR d.sha256 <> p.sha256);

CREATE OR REPLACE PROCEDURE SP_SYNC_DOCS()
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
  n_docs INT; n_chunks INT;
BEGIN
  BEGIN TRANSACTION;
  DELETE FROM ALPHALAKE.DOCS.DOC_PENDING;
  INSERT INTO ALPHALAKE.DOCS.DOC_PENDING SELECT raw, _loaded_at FROM ALPHALAKE.BRONZE.DOC_PARSED_RAW_STREAM;

  DELETE FROM ALPHALAKE.DOCS.DOC_CHUNKS WHERE doc_id IN (SELECT doc_id FROM ALPHALAKE.DOCS.V_DOC_UPDATES);

  INSERT INTO ALPHALAKE.DOCS.DOC_CHUNKS
    SELECT u.doc_id || '-v' || u.version || '-' || c.value:chunk_index::STRING,
           u.doc_id, u.version, c.value:chunk_index::NUMBER, c.value:chunk_type::STRING,
           c.value:section_title::STRING, c.value:page_number::NUMBER, c.value:chunk_text::STRING,
           u.raw:title::STRING, u.raw:doc_type::STRING, u.raw:fund_ticker::STRING, u.raw:access_tier::STRING,
           u.raw:publish_date::DATE,
           SNOWFLAKE.CORTEX.EMBED_TEXT_1024('snowflake-arctic-embed-l-v2.0', c.value:chunk_text::STRING),
           'snowflake-arctic-embed-l-v2.0'
    FROM ALPHALAKE.DOCS.V_DOC_UPDATES u, LATERAL FLATTEN(input => u.raw:chunks) c;
  n_chunks := SQLROWCOUNT;

  MERGE INTO ALPHALAKE.DOCS.DOCUMENTS t
  USING ALPHALAKE.DOCS.V_DOC_UPDATES u ON t.doc_id = u.doc_id
  WHEN MATCHED THEN UPDATE SET version = u.version, sha256 = u.sha256, title = u.raw:title::STRING,
    access_tier = u.raw:access_tier::STRING, chunk_count = ARRAY_SIZE(u.raw:chunks),
    pii_redactions = u.raw:pii_redactions::NUMBER, updated_at = CURRENT_TIMESTAMP()
  WHEN NOT MATCHED THEN INSERT VALUES (u.doc_id, u.version, u.sha256, u.raw:title::STRING, u.raw:doc_type::STRING,
    u.raw:fund_ticker::STRING, u.raw:access_tier::STRING, u.raw:publish_date::DATE, u.raw:source_uri::STRING,
    ARRAY_SIZE(u.raw:chunks), u.raw:pii_redactions::NUMBER, CURRENT_TIMESTAMP());
  n_docs := SQLROWCOUNT;

  COMMIT;
  RETURN 'docs=' || n_docs || ' chunks=' || n_chunks;
EXCEPTION
  WHEN OTHER THEN
    ROLLBACK;
    RAISE;
END;
$$;

CREATE OR REPLACE TASK TASK_SYNC_DOCS
  WAREHOUSE = ALPHALAKE_WH_PIPELINE
  SCHEDULE = '1 MINUTE'
  WHEN SYSTEM$STREAM_HAS_DATA('ALPHALAKE.BRONZE.DOC_PARSED_RAW_STREAM')
AS
  CALL DOCS.SP_SYNC_DOCS();

ALTER TASK TASK_SYNC_DOCS RESUME;

-- Hybrid (vector + keyword) search. Access tiers are enforced by Snowflake RBAC, not by app code:
--   SEARCH_STANDARD   = PUBLIC + INTERNAL docs  -> granted to every persona
--   SEARCH_RESTRICTED = all tiers               -> granted to ALPHALAKE_PM only
-- Personas have no SELECT on DOCS tables, so they cannot bypass the services.
CREATE CORTEX SEARCH SERVICE IF NOT EXISTS SEARCH_STANDARD
  ON chunk_text
  ATTRIBUTES fund_ticker, doc_type, access_tier
  WAREHOUSE = ALPHALAKE_WH_PIPELINE
  TARGET_LAG = '5 minutes'
  EMBEDDING_MODEL = 'snowflake-arctic-embed-l-v2.0'
AS
  SELECT chunk_text, chunk_id, doc_id, title, section_title, page_number, chunk_type, fund_ticker, doc_type,
         access_tier, publish_date
  FROM DOC_CHUNKS WHERE access_tier IN ('PUBLIC', 'INTERNAL');

CREATE CORTEX SEARCH SERVICE IF NOT EXISTS SEARCH_RESTRICTED
  ON chunk_text
  ATTRIBUTES fund_ticker, doc_type, access_tier
  WAREHOUSE = ALPHALAKE_WH_PIPELINE
  TARGET_LAG = '5 minutes'
  EMBEDDING_MODEL = 'snowflake-arctic-embed-l-v2.0'
AS
  SELECT chunk_text, chunk_id, doc_id, title, section_title, page_number, chunk_type, fund_ticker, doc_type,
         access_tier, publish_date
  FROM DOC_CHUNKS;

GRANT USAGE ON CORTEX SEARCH SERVICE SEARCH_STANDARD TO ROLE ALPHALAKE_PM;
GRANT USAGE ON CORTEX SEARCH SERVICE SEARCH_STANDARD TO ROLE ALPHALAKE_ANALYST;
GRANT USAGE ON CORTEX SEARCH SERVICE SEARCH_RESTRICTED TO ROLE ALPHALAKE_PM;
