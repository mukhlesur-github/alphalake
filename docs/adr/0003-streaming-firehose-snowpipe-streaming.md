# ADR-0003: Streaming via Kinesis Firehose → Snowpipe Streaming

- **Status:** Accepted
- **Date:** 2026-11-18

## Context
Price ticks and trade lifecycle events must reach Snowflake within seconds. We want an AWS-native pattern that's common in industry.

## Options considered
1. **Kinesis Data Firehose with the Snowflake destination:** fully managed, built-in retries and an error bucket, uses Snowpipe Streaming internally. Small per-GB cost.
2. **Snowpipe Streaming SDK directly** (Java / Python SDK): cheapest and lowest latency, but we would own buffering, retries, and offsets.
3. **Kafka (MSK) + Snowflake Kafka connector:** the industry standard at scale, but MSK is expensive for a personal project.
4. **Micro-batch files to S3 + Snowpipe:** simple, but latency is minutes and it isn't really streaming.

## Decision
Option 1, with one Firehose stream per event type. JSON lands in `VARIANT` columns; parsing happens downstream.

## Consequences
- Delivery is at-least-once, so **downstream dedupe is mandatory** (MERGE on `event_id`). That's a deliberate learning point.
- Requires a key-pair service user (`SVC_FIREHOSE`) with its private key in Secrets Manager.
- Cost at our volume is cents. Stop the producer when not in use.
- Kafka (MSK) can be added as a stretch comparison later.
