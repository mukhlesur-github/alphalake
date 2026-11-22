-- Live assertions for the hand-written SQL (run after the first full load: `make verify`).

-- 1. SCD2 idempotency: re-running the procedure with nothing new must change nothing.
CALL ALPHALAKE.GOLD.SP_LOAD_DIM_SECURITY();   -- expect snapshots=0 closed=0 inserted=0

-- 2. SCD2 shape: versions per security, the planted reclassification, quarantined bad ISINs
SELECT COUNT(*) total_rows, COUNT(DISTINCT security_id) securities, COUNT_IF(is_current) current_rows
FROM ALPHALAKE.GOLD.DIM_SECURITY;
SELECT security_id, gics_sub_industry, valid_from, valid_to, is_current FROM ALPHALAKE.GOLD.DIM_SECURITY
WHERE security_id IN (SELECT security_id FROM ALPHALAKE.GOLD.DIM_SECURITY WHERE valid_from = '2026-06-30'
                      AND gics_sub_industry = 'Semiconductors') ORDER BY valid_from;
SELECT reason, COUNT(*) FROM ALPHALAKE.SILVER.QUARANTINE_SECURITIES GROUP BY 1;

-- 3. Trade CDC: no duplicate events survived; quarantine reasons; cancelled trades kept as state, not facts
SELECT COUNT(*) - COUNT(DISTINCT event_id) AS duplicate_events FROM ALPHALAKE.SILVER.TRADE_EVENTS;  -- expect 0
SELECT reason, COUNT(*) FROM ALPHALAKE.SILVER.QUARANTINE_TRADE_EVENTS GROUP BY 1;
SELECT status, COUNT(*) FROM ALPHALAKE.SILVER.TRADES_CURRENT GROUP BY 1 ORDER BY 2 DESC;
-- every trade's state equals its highest event_seq (out-of-order safe)  -- expect 0
SELECT COUNT(*) AS state_mismatches FROM ALPHALAKE.SILVER.TRADES_CURRENT t
JOIN (SELECT trade_id, MAX(event_seq) s FROM ALPHALAKE.SILVER.TRADE_EVENTS GROUP BY 1) m ON m.trade_id = t.trade_id
WHERE m.s <> t.last_event_seq;

-- 4. Docs: one version of chunks per doc (no stale vectors)  -- expect 0 rows
SELECT doc_id, COUNT(DISTINCT version) FROM ALPHALAKE.DOCS.DOC_CHUNKS GROUP BY 1 HAVING COUNT(DISTINCT version) > 1;

-- 5. Retrieval: the GTIF limits table is findable
SELECT PARSE_JSON(SNOWFLAKE.CORTEX.SEARCH_PREVIEW('ALPHALAKE.DOCS.SEARCH_STANDARD',
  '{"query": "semiconductor investment limit", "columns": ["title", "section_title", "page_number", "chunk_text"],
    "filter": {"@eq": {"fund_ticker": "GTIF"}}, "limit": 3}')):results AS top_hits;

-- 6. The flagship number
SELECT as_of_date, bucket, actual_pct, limit_pct, is_breach FROM ALPHALAKE.SEMANTIC.COMPLIANCE
WHERE fund_ticker = 'GTIF' AND limit_type = 'SUB_INDUSTRY_MAX' ORDER BY as_of_date DESC LIMIT 3;
