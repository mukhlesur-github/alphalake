# ADR-0001: Snowflake (Enterprise, AWS-hosted) as the warehouse

- **Status:** Accepted
- **Date:** 2026-11-18

## Context
The project needs a cloud data warehouse that handles structured, semi-structured, and unstructured data, supports streaming ingestion, and offers built-in vector and LLM capabilities. The target job description names Snowflake and AWS explicitly.

## Options considered
1. **Snowflake on AWS:** native `VARIANT`, Snowpipe / Snowpipe Streaming, Streams & Tasks, Cortex AI, `VECTOR` type, zero-copy clones, strong governance. Costs credits.
2. **Amazon Redshift:** AWS-native, but weaker semi-structured ergonomics and no equivalent of zero-copy clones. Not named in the JD.
3. **DuckDB locally:** free and fast, but teaches none of the cloud warehouse operations.

## Decision
Snowflake **Enterprise** edition, hosted in the **same AWS region** as our S3 bucket.

## Consequences
- Enterprise edition is required for masking and row access policies.
- Same region avoids egress charges and keeps Snowpipe latency low.
- Must manage cost actively: X-Small warehouses, 60-second auto-suspend, resource monitors.
- After the trial (30 days / ~$400), the account moves to pay-as-you-go. Suspend tasks when not actively working.

## Update (2026-11-22)
The trial account was provisioned as **Standard** edition, where masking and row access policies fail with
`Unsupported feature`. Rather than block on an upgrade, `GOVERNANCE_MODE=views` puts the same rules in a secure view
(`GOLD.DIM_CLIENT`: PII masked and Institutional clients hidden unless the PM or engineer role is in session).
Enterprise remains the target; switching back is `GOVERNANCE_MODE=policies`, `make migrate`, `make dbt-build`.
