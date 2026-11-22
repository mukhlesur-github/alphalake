# ADR-0008: Orchestration with Snowflake Tasks + GitHub Actions

- **Status:** Accepted
- **Date:** 2026-11-18

## Context
We need scheduling for nightly batch runs and dbt, near-real-time processing for streams and documents, and CI for pull requests, on a personal budget.

## Options considered
1. **Amazon MWAA (managed Airflow):** the industry standard, but about $350+/month minimum.
2. **Self-hosted Airflow / Dagster:** free, but needs a running machine (and Docker, which isn't installed).
3. **Snowflake Tasks for in-warehouse work + GitHub Actions for external jobs and CI:** serverless and nearly free.

## Decision
Option 3. Tasks (with `WHEN SYSTEM$STREAM_HAS_DATA`) handle CDC and embedding. GitHub Actions handles nightly generation, upload, `dbt build`, and PR CI (zero-copy clone per PR).

## Consequences
- Orchestration logic is split across two places, so it's documented in the runbook.
- No cross-system dependency graph. A dbt run doesn't wait on Snowpipe; freshness tests guard against stale data instead.
- An optional local Airflow DAG can be written later to learn Airflow concepts.
