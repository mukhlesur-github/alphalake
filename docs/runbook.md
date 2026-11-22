# Runbook: from empty accounts to a working agent

Prerequisite: [setup-accounts.md](setup-accounts.md) done. Each step says which integration it proves.

| # | Command | What happens / what it proves |
|---|---|---|
| 1 | `make tf-init && make tf-apply` | S3 bucket, IAM role, storage integration, database + schemas, warehouses, resource monitor, roles, grants, service users. **Handshake:** the IAM role trusts the integration's IAM user *and* our chosen external ID, so Terraform creates both sides in one apply. Bucket name is written to `.env`. |
| 2 | `make smoke` | Key-pair auth for both service users, persona role with secondary roles off, Cortex embed + complete, S3 access. (`external stage` fails until step 3.) |
| 3 | `make migrate` | Stage, Bronze tables, 9 Snowpipes, streams, CDC + SCD2 + docs procedures and tasks, two Cortex Search services, masking/row-access policies, audit table. |
| 4 | `make wire-snowpipe` | Reads the Snowpipe SQS ARN (`SHOW PIPES` → `notification_channel`) and re-applies Terraform so `s3:ObjectCreated` under `landing/` notifies it. Second apply because the queue only exists once a pipe does. |
| 5 | `make generate docs upload` | 34 months of data, 40k trade events, 20 PDFs → chunked JSON → S3. Snowpipe auto-ingests within ~1 min. |
| 6 | `make backfill` then `make status` | Refreshes pipes (catches anything uploaded before step 4), runs the three tasks once, then resumes the SCD2 task. Re-run `make status` until Silver/Gold/DOCS have rows. |
| 7 | `make dbt-build` | Snapshot + 22 models + 19 tests on top of the Task-built tables, then the semantic view. |
| 8 | `make verify` | Live checks: SCD2 re-run is a no-op, no duplicate events, CDC state = max event_seq, no stale chunks, search finds the GTIF limits table, the flagship number. |
| 9 | `make ask Q="Is GTIF within its semiconductor limit?"` | Agent: metric tool SQL + Cortex Search + Cortex COMPLETE, cited. Try `ROLE=ALPHALAKE_ANALYST` and `MODE=sql`. |
| 10 | `make app` | Streamlit on localhost:8501: persona switcher, fund charts, ask, governance demo, pipeline health. |
| 11 | `make stream` then (≈2 min) `make dbt-build` | Live trades with duplicates, out-of-order, malformed, corrections and busts → quarantine + correct state → new positions. |

## Demos worth running

- **Governance:** Clients tab as PM vs Analyst (masked PII, Institutional rows hidden). Ask "What did the investment committee decide about GTIF?" as both: only PM can reach the RESTRICTED minutes.
- **Prompt injection:** ask about "semiconductor supply chain lead times". The poisoned research note is retrieved but dropped (`poisoned_chunk_dropped` flag).
- **Document update:** edit a prospectus in `src/alphalake/generators/documents.py`, `make docs upload`. Only the changed PDF is re-parsed (v2), and its v1 chunks disappear in the same transaction.
- **Point in time:** `SELECT * FROM SEMANTIC.COMPLIANCE WHERE fund_ticker='GTIF' AND limit_type='SUB_INDUSTRY_MAX' ORDER BY as_of_date` jumps on 2026-06-30, because of the SCD2 reclassification, not a trade.

## When something breaks

| Symptom | Look at |
|---|---|
| Files in S3, Bronze empty | `SELECT SYSTEM$PIPE_STATUS('ALPHALAKE.BRONZE.PIPE_PRICES')`; `SELECT * FROM TABLE(ALPHALAKE.INFORMATION_SCHEMA.COPY_HISTORY(TABLE_NAME=>'BRONZE.PRICES_RAW', START_TIME=>DATEADD(hour,-2,CURRENT_TIMESTAMP())))`; bucket notification exists (`make wire-snowpipe`) |
| `LIST @BRONZE.LANDING` access denied | `DESC INTEGRATION ALPHALAKE_S3_INT` (STORAGE_AWS_IAM_USER_ARN / EXTERNAL_ID) vs the IAM role trust policy |
| Task not running | `SHOW TASKS IN DATABASE ALPHALAKE` (state), `TASK_HISTORY()` error_message, `EXECUTE TASK ...` to run now |
| SCD2 snapshot skipped | `SILVER.QUARANTINE_SECURITIES` with reason "older than SCD2 watermark" |
| Agent errors | `flags` in the answer / `AUDIT.AGENT_INTERACTIONS.guardrail_flags`; try another `CORTEX_LLM_MODEL` |
| Credits | Snowsight → Admin → Cost Management; `ALPHALAKE_RM` suspends warehouses at 95% |
