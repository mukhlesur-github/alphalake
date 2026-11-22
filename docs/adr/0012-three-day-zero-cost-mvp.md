# ADR-0012: 3-day, $0 MVP scope

- **Status:** Accepted (partially supersedes 0002, 0003, 0004, 0006, 0008, 0010)
- **Date:** 2026-11-18

## Context
The platform must be built in 2–3 days at $0: a Snowflake 30-day trial (Enterprise, AWS) and the AWS Free plan,
both deleted afterwards. The goal is to see every component **integrated end to end**, not to run production.

## Decision
| Area | Full design | MVP |
|---|---|---|
| LLM | GPT-4o on Microsoft Foundry (0006) | **Snowflake Cortex `COMPLETE`** (trial credits), model set by `CORTEX_LLM_MODEL` (default `openai-gpt-4.1`, cross-region enabled; see Update) |
| Streaming | Firehose → Snowpipe Streaming (0003) | Producer writes **micro-batch JSONL files** to S3 every 10 s → Snowpipe → same Stream + Task CDC graph |
| Documents | S3 → SQS → Lambda (0004) | The same PyMuPDF parser + SHA-256 sync runs **locally** (`make docs`), publishes chunked JSON to S3 → Snowpipe |
| Migrations | schemachange (0002) | ~50-line runner (`alphalake migrate`) with the same `V###__name.sql` convention + history table |
| SCD2 #2 | dbt snapshot for `DIM_FUND` (0005) | `DIM_FUND` rebuilt declaratively from snapshot history (a snapshot can't backfill 34 months in one run); dbt snapshot used for `DIM_CLIENT` |
| Doc access | access_tier filter in the RAG tool | **Two Cortex Search services** (standard / restricted) granted per role; personas have no SELECT on `DOCS` tables |
| Orchestration | Tasks + GitHub Actions (0008) | Tasks only; dbt run by hand (`make dbt-build`) |
| UI | local → Streamlit in Snowflake (0010) | Local only (see Update) |
| Environments | dev + prod | One database `ALPHALAKE` |
| Terraform state | S3 + DynamoDB | Local state |

Dropped for now: Firehose, Lambda/SQS/DLQ, CI/CD, SiS, price-tick stream, `DIM_FUND_MANAGER`, full eval harness.

## Consequences
- Every integration point that matters is still real: IAM ↔ storage-integration trust, S3 → Snowpipe auto-ingest,
  Streams + Tasks CDC, hand-written SCD2, dbt on Task-built tables, semantic layer, Cortex embeddings + search,
  RBAC-enforced RAG, and an agent running under the end user's role.
- Swapping back to the full design changes only the ingestion edges: the Bronze tables and everything
  downstream stay the same (Firehose and Lambda write the same payloads).

## Update (2026-11-22): what changed when it ran on the live accounts
- **Snowflake setup moved out of Terraform** into an idempotent `infra/snowflake/setup.sql` run once as ACCOUNTADMIN
  (no Terraform service user). Terraform now manages AWS only. The storage integration uses an external ID we choose,
  so it can be created before the IAM role.
- **LLM:** new accounts can't call legacy `SNOWFLAKE.CORTEX.COMPLETE`, so the agent uses `AI_COMPLETE`.
  `openai-gpt-4.1` was retired; the default is `claude-sonnet-4-5`.
- **Edition:** the trial came up as Standard, not Enterprise, so masking and row access policies are unavailable.
  `GOVERNANCE_MODE=views` builds `GOLD.DIM_CLIENT` as a secure view with the same rules (see ADR-0001).
- **Streamlit in Snowflake** was added after all: one warehouse-runtime app per persona (`infra/snowflake/streamlit.sql`).
- **Uploads from the Snowsight Workspace** (no AWS credentials) relay through `@BRONZE.LANDING_INTERNAL` and `COPY FILES` into S3.
