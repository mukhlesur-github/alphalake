# Architecture Decision Records

Each ADR records one decision: the context, the options considered, the decision, and its consequences. ADRs are immutable once accepted. To change a decision, write a new ADR that supersedes the old one.

| # | Decision | Status |
|---|---|---|
| [0001](0001-snowflake-on-aws.md) | Snowflake (Enterprise, AWS-hosted) as the warehouse | Accepted |
| [0002](0002-iac-split-terraform-schemachange-dbt.md) | IaC split: Terraform / schemachange / dbt | Accepted |
| [0003](0003-streaming-firehose-snowpipe-streaming.md) | Streaming via Kinesis Firehose → Snowpipe Streaming | Accepted |
| [0004](0004-event-driven-docs-s3-sqs-lambda.md) | Event-driven document pipeline: S3 → SQS → Lambda, PyMuPDF, SHA-256 sync | Accepted |
| [0005](0005-medallion-kimball-scd2.md) | Medallion layers, Kimball Gold layer, SCD2 two ways (hand-written MERGE + dbt snapshots) | Accepted |
| [0006](0006-cortex-embeddings-foundry-gpt4o.md) | Cortex for embeddings/search, GPT-4o on Foundry for generation | Accepted |
| [0007](0007-semantic-views-governed-sql-modes.md) | Snowflake semantic views + two governed SQL modes (tool calling, validated text-to-SQL) | Accepted |
| [0008](0008-orchestration-tasks-github-actions.md) | Orchestration: Snowflake Tasks + GitHub Actions | Accepted |
| [0009](0009-security-keypair-rbac-governance.md) | Security: key-pair auth, layered RBAC, policy-based governance | Accepted |
| [0010](0010-streamlit-local-then-sis.md) | Streamlit: local first, then Streamlit in Snowflake | Accepted |
| [0011](0011-langgraph-agent-role-inheritance.md) | LangGraph research agent that inherits the user's role | Accepted |
| [0012](0012-three-day-zero-cost-mvp.md) | 3-day, $0 MVP scope (Cortex COMPLETE, file micro-batches, local doc parsing) | Accepted |

Template: [`template.md`](template.md)
