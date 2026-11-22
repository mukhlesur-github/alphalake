# AlphaLake

**An enterprise-style Data & GenAI platform for a (fictional) asset management company — built on Snowflake + AWS.**

AlphaLake ingests structured, semi-structured, and unstructured data through batch, streaming, and event-driven pipelines; models it into a governed Snowflake warehouse with a semantic layer; and exposes it through a Streamlit app with an AI assistant that answers questions using both warehouse metrics and documents — with citations.

> Status: **3-day MVP built, not yet run against live accounts** ([ADR-0012](docs/adr/0012-three-day-zero-cost-mvp.md)).
> Local parts are tested (`make test`: 31 passing). Next: create the accounts ([setup](docs/setup-accounts.md)) and follow the [runbook](docs/runbook.md).

## Quick start

```bash
make install generate docs test     # everything that runs without accounts
make bootstrap-sql                  # then: tf-apply, migrate, wire-snowpipe, upload, backfill, dbt-build, verify, app
make help
```

---

## The business story

*Northwind Capital* (fictional) runs 12 mutual funds. Its data is scattered:

| Data | Shape | Arrives via |
|---|---|---|
| Securities master, funds, clients, accounts | Structured (CSV) | Nightly batch files |
| Custodian holdings snapshots | Structured (Parquet) | Nightly batch files |
| Trade executions & lifecycle events | Semi-structured (nested JSON) | Real-time stream |
| Market price ticks | Semi-structured (JSON) | Real-time stream |
| Prospectuses, research notes, compliance policies, client emails | Unstructured (PDF / HTML / text) | Dropped into S3 at any time |

A portfolio manager should be able to ask:

> *"What is the Global Tech Innovation Fund's current exposure to semiconductors, and does it breach the sector limit in its prospectus?"*

…and get one answer that combines **governed warehouse numbers** (exposure from holdings) with **document evidence** (the limit from the prospectus PDF), with the SQL and source passages shown.

---

## Architecture at a glance

```
  AWS                                                           Snowflake (AWS region)                          App
  ───                                                           ──────────────────────                          ───
  Generators ─batch──▶ S3 landing/batch ──Snowpipe────────────▶ BRONZE ─┐
             ─stream─▶ Kinesis Firehose ──Snowpipe Streaming──▶ BRONZE ─┼─▶ SILVER ─▶ GOLD ─▶ SEMANTIC ─┐   Streamlit
             ─docs───▶ S3 landing/docs ─▶ SQS ─▶ Lambda ──────▶ BRONZE ─┘  (Streams & Tasks,  (star     │   + LangGraph agent
                                     (PyMuPDF, SHA-256,                     FLATTEN, QUALIFY) schema,   ├─▶ SQL tool  (user's role)
                                      PII redaction)                                          SCD2)     │   RAG tool  (pre-filtered)
                                                                DOCS: chunks + VECTOR ─▶ Cortex Search ─┘
                                                                                                             GPT-4o on Microsoft Foundry
```

Full detail: [`docs/architecture.md`](docs/architecture.md)

---

## Tech stack

| Concern | Choice |
|---|---|
| Warehouse | Snowflake (Enterprise edition, hosted on AWS) |
| Cloud | AWS — S3, IAM, Budgets (MVP); SQS, Lambda, Kinesis Data Firehose, Secrets Manager in the full design |
| Infrastructure as Code | Terraform (AWS + Snowflake providers), versioned SQL migrations (`alphalake migrate`) |
| Layers | Medallion: Bronze → Silver → Gold (Kimball star schema) → Semantic |
| Transformation | Streams & Tasks with hand-written SQL (CDC, SCD2 MERGE) + dbt Core (`dbt-snowflake`) |
| CDC / incremental | Snowflake Streams, Tasks, Dynamic Tables |
| Semantic layer | Snowflake semantic views + `metrics.yml` registry |
| Document parsing | PyMuPDF (layout-aware, tables → markdown), SHA-256 incremental sync, PII redaction |
| Embeddings & vector search | Snowflake Cortex `EMBED_TEXT_1024`, `VECTOR` type, Cortex Search (hybrid vector + BM25) |
| Agent | LangGraph: SQL tool (tool calling / governed text-to-SQL) + RAG tool; inherits the user's Snowflake role |
| LLM | Snowflake Cortex `COMPLETE` (MVP; GPT-4o on Foundry in the full design) |
| UI | Streamlit (local → Streamlit in Snowflake) |
| Language | Python 3.12 (Pydantic v2, asyncio), SQL |
| Quality | dbt tests, pytest, ruff, mypy, pre-commit, RAG/agent eval harness |
| CI/CD | GitHub Actions |

---

## How the JD skills map to the project

| Skill | Where it shows up |
|---|---|
| Python & SQL | Pydantic contracts, asyncio backfill with backoff, Lambda, LangGraph agent; hand-written `MERGE` (SCD2), `QUALIFY ROW_NUMBER()`, `LATERAL FLATTEN`, window functions, point-in-time joins |
| Batch / Streaming / Event-driven pipelines | Snowpipe auto-ingest / Firehose → Snowpipe Streaming / S3 → SQS → Lambda |
| Embeddings, vector search, RAG | Layout-aware chunking, Cortex embeddings, `VECTOR` similarity + Cortex Search hybrid retrieval with metadata pre-filters, incremental vector sync, GPT-4o agent, evaluation harness |
| Dimensional modelling & semantic layer | Medallion + Kimball star schema, SCD2 (hand-written MERGE and dbt snapshots), Snowflake semantic views, governed SQL for the AI |
| Snowflake, AWS, warehousing | Storage integrations (no AWS keys), pipes, streams, tasks, dynamic tables, RBAC, masking, row access, zero-copy clones, resource monitors |
| Structured / semi-structured / unstructured | CSV + Parquet, nested JSON via `VARIANT`, PDFs (with tables)/HTML/text via parsing + chunking |

---

## Documentation

| Doc | Contents |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Components, data flows, Snowflake & AWS object design, security, observability |
| [`docs/data-model.md`](docs/data-model.md) | Source entities, synthetic data spec, star schema, document corpus |
| [`docs/phases.md`](docs/phases.md) | Phase-by-phase build plan with learning goals and done criteria |
| [`docs/setup-accounts.md`](docs/setup-accounts.md) | Snowflake, AWS, Foundry, and local tooling setup checklist |
| [`docs/adr/`](docs/adr/) | Architecture Decision Records — why each choice was made |

---

## Repository layout (MVP)

```
├── infra/terraform/        # AWS (bucket, IAM role, budget) + Snowflake (DB, schemas, warehouses, RBAC, users, integration)
├── infra/bootstrap/        # one-time SQL for the Terraform service user
├── snowflake/migrations/   # V001 bronze+pipes · V002 trade CDC · V003 SCD2 DIM_SECURITY · V004 docs+Cortex Search · V005 governance
├── snowflake/ops/          # backfill, status, live verification SQL
├── dbt/                    # staging → intermediate → GOLD star schema → SEMANTIC views (+ semantic view macro), tests
├── src/alphalake/
│   ├── generators/         # universe, prices/FX, portfolios → trades + custodian holdings, trade-event contract, PDFs
│   ├── producers/          # S3 uploader, live trade stream (micro-batch files)
│   ├── docs/               # PyMuPDF layout-aware parser, PII redaction, SHA-256 incremental sync
│   ├── agent/              # metric catalogue (tool calling), sqlglot guard, Cortex backends, LangGraph graph
│   └── common/             # settings, key-pair connections, migration runner, smoke test
├── app/streamlit_app.py
├── tests/                  # 31 offline tests
├── scripts/                # key generation, bootstrap render, Terraform ↔ .env / Snowpipe wiring
└── Makefile
```
