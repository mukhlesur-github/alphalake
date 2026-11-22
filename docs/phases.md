# Build Plan

## MVP (3 days, $0): current plan

Scope and deviations: [ADR-0012](adr/0012-three-day-zero-cost-mvp.md). Code for all three days is written; local parts are tested.
Running it against the accounts follows the [runbook](runbook.md).

| Day | Build | Status |
|---|---|---|
| 1 | Accounts, Terraform (S3, IAM ↔ storage integration, RBAC, warehouses, users), migrations, Snowpipe wiring, synthetic data, Bronze | Code done · needs accounts |
| 2 | Trade CDC (Streams + Tasks), hand-written SCD2, dbt Silver/Gold/SEMANTIC, semantic view, tests | Code done · needs accounts |
| 3 | Documents → Cortex Search (two tiered services), LangGraph agent (tool calling + governed text-to-SQL), Streamlit | Code done · agent graph tested with fakes |

Phases 0–8 below are the full design; the MVP covers the core of Phases 0–3 and 5–7 and part of Phase 4 (file micro-batches instead of Firehose).

---

Each phase ends with something **working end to end** that you can demo, and a short entry in `docs/learning-log.md` (what you learned, what broke, what you'd do differently).

**Core = Phases 0–7.** That's a complete, interview-ready platform. Phase 8 is enterprise hardening; stretch work is optional.

Effort estimates assume a few focused hours per session, for your planning only.

---

## Phase 0: Foundations (≈1–2 sessions)

**Goal:** accounts, repo, IaC skeleton, security baseline, cost guardrails.

- Repo scaffold: `pyproject.toml` (uv), ruff, mypy, pytest, pre-commit, Makefile, `.env.example`, `.gitignore`, `pydantic-settings` config, structured logging
- Snowflake (Terraform): databases, medallion schemas, warehouses, resource monitors, RBAC (access + functional/persona roles), service users with key-pair auth
- AWS (Terraform): remote state (S3 + DynamoDB lock), landing bucket, AWS Budget alert
- Smoke tests: Python → Snowflake (key-pair), Python → Foundry GPT-4o, Cortex `EMBED_TEXT_1024` available in your region

**Learn:** Terraform (providers, state, modules, tfvars), the Snowflake RBAC model, key-pair auth.
**Done when:** `make plan ENV=dev` is clean, `make smoke` passes all three checks, and the resource monitor is visible in Snowsight.

---

## Phase 1: Synthetic data (≈2 sessions)

**Goal:** realistic, reproducible (seeded) data for all entities.

- Pydantic models for every entity and event (they double as data contracts later)
- Reference data: securities, issuers, fund managers, funds, limits, benchmarks, clients, accounts, advisors, including **SCD2-triggering changes** over time (rating changes, sector reclassifications, manager moves)
- Market simulation: correlated GBM prices, FX
- Portfolio simulation: trades that drive holdings; NAV and flows; planted compliance breaches
- Custodian holdings with deliberate recon breaks
- Chaos knobs: duplicate %, late %, malformed %, bad-ISIN %, schema drift
- Unit tests: referential integrity, weights ≈ 100%, determinism with a fixed seed

**Learn:** data simulation, Parquet vs CSV, how asset-management data fits together.
**Done when:** `make generate` writes 3 years of data locally in under 5 minutes, and the tests pass.

---

## Phase 2: Batch ingestion to Bronze (≈1–2 sessions)

**Goal:** files in S3 load into Bronze automatically, with no AWS keys anywhere.

- Terraform: IAM role ↔ storage integration trust (the external ID handshake), external stages, S3 event notification → Snowpipe SQS
- schemachange: file formats, Bronze tables with load metadata columns, pipes
- Uploader: `make upload-batch DATE=…` (Hive-style partitions)
- Manual `COPY INTO` first (to understand it), then Snowpipe auto-ingest
- Monitoring queries: `COPY_HISTORY`, `SYSTEM$PIPE_STATUS`
- Re-upload test: the same file isn't loaded twice

**Learn:** storage integrations, external stages, `COPY INTO` options, Snowpipe, load metadata.
**Done when:** dropping a file in S3 makes rows appear in Bronze within about 1 minute.

---

## Phase 3: Silver, Gold, and the semantic layer (≈3–4 sessions)

**Goal:** a trustworthy star schema with SCD2 and governed metrics.

- **Hand-written SCD2:** stored procedures + Tasks with idempotent `MERGE` for `DIM_SECURITY` and `DIM_FUND_MANAGER`; idempotency test (re-run → zero changes)
- dbt project setup: profiles with key-pair auth, `generate_schema_name`, sources (including the Task-built tables)
- Silver models (staging + `int_*`): typing, positions from trades, price forward-fill, FX conversion
- dbt snapshots for `DIM_FUND`, `DIM_CLIENT`; compare them with the hand-written MERGE in the learning log
- Gold facts (transaction, periodic snapshot, accumulating snapshot) with point-in-time joins
- Tests: generic + dbt_expectations + reconciliation + compliance + SCD2 integrity + point-in-time
- Semantic views in `SEMANTIC` + `semantic/metrics.yml`
- `dbt docs generate`; artifacts → `AUDIT.DBT_RUNS`

**Learn:** Kimball modelling, SCD2 (by hand and with a framework), `MERGE`, incremental strategies, dbt testing, semantic views.
**Done when:** `dbt build` is green, the SCD2 idempotency test passes, and the semantic view answers "GTIF sector exposure on date X" matching a hand-written query.

---

## Phase 4: Streaming and CDC (≈2 sessions)

**Goal:** live trades and prices land in seconds, with correct state.

- Terraform: two Firehose streams with a Snowflake destination, error bucket, Secrets Manager secret
- Stream producer: `make stream RATE=50` (ticks/sec plus trade lifecycle events, with chaos knobs); Pydantic-validated, async batching with backoff
- Stream + Task graph:
  - `LATERAL FLATTEN` fills, schema checks → `QUARANTINE`
  - `QUALIFY ROW_NUMBER()` dedupe
  - `MERGE` into `TRADES_CURRENT` (ordering, corrections, cancels)
- Dynamic Table for latest prices; compare cost and latency with Streams & Tasks
- Incremental dbt models pick up new trades into `FACT_PORTFOLIO_TRADES`

**Learn:** Firehose, Snowpipe Streaming, Streams (offsets, staleness), Tasks (graphs, `WHEN`), Dynamic Tables, at-least-once vs exactly-once.
**Done when:** a cancelled trade disappears from the fact table, and duplicate, out-of-order, and malformed events produce correct state and quarantine rows (asserted by tests).

---

## Phase 5: Event-driven unstructured pipeline (≈3 sessions)

**Goal:** dropping a document into S3 makes it searchable within about a minute; modifying it replaces its vectors.

- Document generators: prospectuses and fact sheets (with tables), manager commentary, earnings transcripts, research, policies, minutes, emails, poisoned docs, plus `golden_set.jsonl`
- `alphalake.docs` package: Pydantic models, PyMuPDF layout-aware parser (text blocks + tables → markdown), PII redactor, SHA-256 sync logic
- Terraform: SQS + DLQ, Lambda (zip packaging, IAM, env), S3 notification on `docs/raw/`
- Lambda handler: validate → hash check → parse → redact → write parsed JSON; partial batch failures
- Snowflake: Snowpipe → `BRONZE.DOC_PARSED_RAW` → Stream + Task: **delete stale chunks** → layout-aware chunking → `EMBED_TEXT_1024` → `DOC_CHUNKS` (one transaction)
- Cortex Search service with metadata attributes
- `make reindex`: async backfill CLI (semaphore-bounded concurrency, exponential backoff with jitter)
- Tests: parser on sample PDFs (tables survive), PII redaction, idempotent re-upload, modified-document vector replacement, DLQ behaviour

**Learn:** event-driven design, SQS semantics (visibility timeout, DLQ, partial failures), Lambda packaging, layout-aware PDF parsing, chunking strategies, embeddings, hybrid search, asyncio.
**Done when:** you upload a prospectus and a Cortex Search query filtered on `fund_ticker` returns its limits table within about 2 minutes, and re-uploading a modified version leaves no stale chunks.

---

## Phase 6: LangGraph research agent (≈3–4 sessions)

**Goal:** a grounded, cited, governed AI agent.

- LangGraph state graph: guardrails → router → tools → synthesis → output checks (bounded retries)
- GPT-4o via `AzureChatOpenAI` (Foundry); `LLMProvider` abstraction with Cortex `COMPLETE` as an alternative
- **Metric tool, default mode:** Pydantic tool schema from `metrics.yml` → deterministic SQL compiler (unit-tested)
- **Metric tool, advanced mode:** governed text-to-SQL → `sqlglot` validator (single SELECT, `SEMANTIC.*` only, row limit)
- **RAG tool:** Cortex Search with metadata pre-filters (fund_ticker, quarter, doc_type) + mandatory `access_tier`
- **Role inheritance:** all queries run under the user's persona role
- Output contract: page citations + SQL lineage + route; numbers checked against SQL results
- Logging to `AUDIT.AGENT_INTERACTIONS`
- Evaluation harness (`make eval`, async): routing, hit@k / MRR, SQL accuracy for both modes, numeric accuracy, faithfulness (LLM judge), citation correctness, security, injection resistance

**Learn:** agent design with LangGraph, tool calling, text-to-SQL safety, hybrid retrieval, prompt-injection defense, evaluation methodology.
**Done when:** `make eval` runs and stores results; the flagship question ("Is GTIF within its semiconductor limit?") returns the SQL number + prospectus page citation; and the `ANALYST_RESTRICTED` persona cannot get restricted content or unmasked PII through the agent.

---

## Phase 7: Streamlit app (≈2 sessions)

**Goal:** a demo-ready UI.

- Pages: Overview, Fund detail, Live market, Ask AlphaLake, Data quality, Pipeline & cost, Eval
- Persona switcher demonstrating masking, row access, and document tiers on the same question
- SQL-mode toggle (tool calling vs governed text-to-SQL)
- Feedback buttons → audit table

**Learn:** Streamlit state and caching, building on a semantic layer, UX for AI answers (showing sources and lineage).
**Done when:** the app runs locally against DEV with live data on every page.

---

## Phase 8: Production hardening (≈2–3 sessions)

**Goal:** it looks and behaves like an enterprise platform.

- CI/CD: GitHub Actions with OIDC to AWS; zero-copy clone per PR; `dbt build --select state:modified+`; `terraform plan` as a PR comment
- Scheduled prod runs (nightly batch + dbt)
- Observability: task failure alerts, DLQ alarm, cost dashboard
- Deploy to Streamlit in Snowflake (external access integration + secret for Foundry; role-inheritance approach for SiS)
- Runbook (`docs/runbook.md`): replay a failed pipe, reprocess a document, re-embed after a model change, rotate keys, teardown
- README polish: architecture image, screenshots, demo script

**Learn:** CI/CD for data, environment promotion, operational readiness.
**Done when:** a PR triggers a full CI build on a clone, prod runs nightly unattended, and `make destroy` cleans everything up.

---

## Stretch ideas (optional)

- Snowflake Cortex Analyst on the same semantic views, compared with our two SQL modes in the eval
- dbt MetricFlow locally (`dbt-metricflow` CLI), compared with semantic views
- Docling or Cortex `PARSE_DOCUMENT` compared with PyMuPDF on table-heavy PDFs
- Apache Iceberg tables on S3 (open table format)
- Local Airflow DAG for orchestration comparison
- Kafka (MSK Serverless) compared with Firehose
- Multi-turn agent memory with conversation summaries
