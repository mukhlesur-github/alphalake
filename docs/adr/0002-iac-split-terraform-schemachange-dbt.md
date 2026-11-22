# ADR-0002: IaC split (Terraform / schemachange / dbt)

- **Status:** Accepted
- **Date:** 2026-11-18

## Context
Everything should be reproducible from code. Snowflake objects differ in how they change: account-level objects (roles, warehouses) are declarative and rarely change; schema objects (pipes, streams, tasks, policies) are often easier to manage as ordered SQL; transformations change daily.

## Options considered
1. **Terraform for everything:** a single tool, but the Snowflake provider is awkward for tasks, streams, and policies, and plans become noisy.
2. **SQL scripts for everything:** simple, but no state, drift detection, or cross-cloud wiring (the IAM ↔ storage integration handshake).
3. **Split by object type:** Terraform for cloud and account-level objects, schemachange for versioned schema migrations, dbt for transformations.

## Decision
Option 3:

| Tool | Manages |
|---|---|
| Terraform (`aws`, `snowflake` providers) | All AWS resources; Snowflake databases, schemas, warehouses, resource monitors, roles, grants, users, integrations |
| schemachange | Bronze tables, file formats, stages, pipes, streams, tasks, SCD2 MERGE procedures, dynamic tables, semantic views, policies, tags |
| dbt | Silver → Gold models (except Task-built tables), snapshots, tests |

## Consequences
- This mirrors how many enterprise Snowflake teams work, so it's good learning.
- Ordering matters: Terraform first, then schemachange, then dbt. The Makefile encodes this order.
- Terraform remote state lives in S3 with DynamoDB locking.
