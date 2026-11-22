# ADR-0004: Event-driven document pipeline (S3 → SQS → Lambda)

- **Status:** Accepted
- **Date:** 2026-11-18

## Context
Documents arrive at unpredictable times. Each one must be validated, parsed (including financial tables), PII-redacted, chunked, and embedded automatically, with retries, no duplicates, and no stale vectors when a document changes.

## Options considered
1. **S3 → Lambda directly:** simplest, but limited retry control and no buffering.
2. **S3 → SQS → Lambda:** buffering, batching, visibility-timeout retries, and a dead-letter queue.
3. **S3 → SNS → (SQS → Lambda, + other subscribers):** fan-out to several consumers, at the cost of one more hop.
4. **Long-running Python watcher polling the prefix:** easy to write, but it's polling, not event-driven, and needs an always-on host.
5. **Snowflake-only (directory table + Cortex `PARSE_DOCUMENT`):** less AWS code, but it hides the event-driven pattern and can't redact PII before data enters Snowflake.

## Decision
Option 2, with these engineering standards:
- **Pydantic** models for the S3 event, metadata, and parsed output
- **PyMuPDF** layout-aware parsing: reading-order text blocks, headings, and `find_tables()` → markdown, so table numbers stay aligned
- **SHA-256 incremental sync:** an unchanged file is skipped; a changed file becomes a new version, and downstream **deletes the old version's chunks in the same transaction** as the insert
- PII redaction **before** data leaves Lambda
- Partial batch failure reporting, a DLQ after 3 receives, and a quarantine prefix

Lambda writes parsed JSON to `docs/parsed/`, which Snowpipe loads. Chunking and embedding happen in Snowflake (Stream + Task + Cortex). The same `alphalake.docs` package powers an **asyncio backfill CLI** (bounded concurrency, exponential backoff) for re-indexing.

## Consequences
- S3 notification prefixes must not overlap: `docs/raw/` → our SQS; `batch/` and `docs/parsed/` → Snowpipe's SQS.
- PyMuPDF must be packaged as manylinux wheels in the Lambda zip. Docling is too heavy for zip Lambda, so it stays a stretch comparison.
- PyMuPDF is AGPL-licensed, which is fine for a personal learning project; a commercial product would need a license or an alternative.
