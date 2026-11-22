# Runbook: from empty accounts to a working agent

Prerequisite: [setup-accounts.md](setup-accounts.md) done. Each step says which integration it proves.

| # | Command | What happens / what it proves |
|---|---|---|
| 0 | `make snowflake-sql`, then run `infra/snowflake/setup.sql` as ACCOUNTADMIN | Database + schemas, warehouses, resource monitor, roles, grants, service users, storage integration `ALPHALAKE_S3_INT` (our chosen external ID). Copy `STORAGE_AWS_IAM_USER_ARN` from `DESC INTEGRATION ALPHALAKE_S3_INT` into `terraform.tfvars`. |
| 1 | `make tf-init && make tf-apply` | AWS only: S3 bucket, IAM role, budget. **Handshake:** the IAM role trusts the integration's IAM user *and* our chosen external ID. Bucket name is written to `.env`. |
| 2 | `make smoke` | Key-pair auth for both service users, persona role with secondary roles off, Cortex embed + `AI_COMPLETE` with `CORTEX_LLM_MODEL`, S3 access from this machine (`aws s3`; needs the `alphalake` AWS profile, irrelevant if you only upload from the Workspace). (`external stage` fails until step 3.) |
| 3 | `make migrate` | Stage, Bronze tables, 9 Snowpipes, streams, CDC + SCD2 + docs procedures and tasks, two Cortex Search services, masking/row-access policies (`GOVERNANCE_MODE=policies` only), audit table. |
| 4 | `make wire-snowpipe` | Reads the Snowpipe SQS ARN (`SHOW PIPES` → `notification_channel`) and re-applies Terraform so `s3:ObjectCreated` under `landing/` notifies it. Second apply because the queue only exists once a pipe does. |
| 5 | `make generate docs upload` | 34 months of data, 40k trade events, 20 PDFs → chunked JSON → S3. Snowpipe auto-ingests within ~1 min. |
| 6 | `make backfill` then `make status` | Refreshes pipes (catches anything uploaded before step 4), runs the three tasks once, then resumes the SCD2 task. Re-run `make status` until Silver/Gold/DOCS have rows. |
| 7 | `make dbt-build` | Snapshot + 22 models + 19 tests on top of the Task-built tables, then the semantic view. `GOLD.DIM_CLIENT` is a table with policies (Enterprise) or a secure view (`views`, the `dbt_project.yml` default). |
| 8 | `make verify` | Live checks: SCD2 re-run is a no-op, no duplicate events, CDC state = max event_seq, no stale chunks, search finds the GTIF limits table, the flagship number. |
| 9 | `make ask Q="Is GTIF within its semiconductor limit?"` | Agent: metric tool SQL + Cortex Search + `AI_COMPLETE`, cited. Try `ROLE=ALPHALAKE_ANALYST` and `MODE=sql` (tool mode only answers from the metric catalogue; free-form questions such as trade counts per day need `MODE=sql`). |
| 10 | `make app` | Streamlit on localhost:8501: persona switcher, fund charts, ask, governance demo, pipeline health. |
| 10b | upload `app/` + `src/alphalake/` to `@ALPHALAKE.APP.CODE`, then run `infra/snowflake/streamlit.sql` as ACCOUNTADMIN | Streamlit in Snowflake: one app per persona (`ALPHALAKE.APP.ALPHALAKE_PM`, `ALPHALAKE.APP.ALPHALAKE_ANALYST`), because warehouse-runtime apps run as their owner's role. Re-upload the code after changing it. |
| 11 | `make stream` then (≈2 min) `make dbt-build` | Live trades with duplicates, out-of-order, malformed, corrections and busts → quarantine + correct state → new positions. If the tasks are suspended, run `EXECUTE TASK ALPHALAKE.SILVER.TASK_PROCESS_TRADE_EVENTS` first. |

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
| Agent errors | `flags` in the answer / `AUDIT.AGENT_INTERACTIONS.guardrail_flags`; `The model ... has been in legacy state` means it was retired: set another `CORTEX_LLM_MODEL` (see setup) |
| Analyst sees unmasked PII | `DIM_CLIENT` was built in `policies` mode on Standard edition (policies don't exist, so nothing is attached). Rebuild with `GOVERNANCE_MODE=views` |
| Silver / Gold not updating | Tasks are suspended (`SHOW TASKS IN DATABASE ALPHALAKE`) to save credits: `make backfill`, or `EXECUTE TASK` / `ALTER TASK ... RESUME` |
| Credits | Snowsight → Admin → Cost Management; `ALPHALAKE_RM` suspends warehouses at 95% |

### Switched to S3 (2026-11-22)

`BRONZE.LANDING` is now the S3 stage on `s3://alphalake-landing-795031850612/landing/` (integration `ALPHALAKE_S3_INT`,
AWS account 795031850612, ap-southeast-1) with 9 auto-ingest pipes; the bucket notification on `landing/` targets the
pipes' SQS queue (`SHOW PIPES` -> `notification_channel`). The former internal stage is kept as `BRONZE.LANDING_INTERNAL`;
history was moved with `COPY FILES` *before* the notification existed, so nothing was loaded twice. Never run
`ALTER PIPE ... REFRESH` on these pipes (it would reload history). From the sandbox, uploads relay
`PUT @LANDING_INTERNAL` -> `COPY FILES` -> S3; from a laptop with AWS credentials, `make upload` writes to S3 directly.

### End-to-end check (2026-11-22)

All steps above ran on the live accounts. A 30-second `stream` (258 events) landed in S3, Snowpipe loaded it in ~45 s,
the CDC task kept 247 events (10 duplicates dropped, 1 quarantined), `make dbt-build` passed 42/42, `make verify`
passed, and the agent answered from the new trades. The three tasks are left suspended between runs to save credits.
