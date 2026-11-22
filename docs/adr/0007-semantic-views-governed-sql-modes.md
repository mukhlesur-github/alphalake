# ADR-0007: Semantic views + two governed SQL modes for the agent

- **Status:** Accepted
- **Date:** 2026-11-18

## Context
The agent must answer numeric questions ("What is GTIF's NAV?", "Tech exposure across European equity funds this quarter?") correctly, consistently with dashboards, and within governance. LLMs hallucinate metric definitions and joins when given raw tables.

## Options considered
**Semantic layer technology**
1. **dbt Semantic Layer / MetricFlow:** good metric modelling, but its query APIs need dbt Cloud; dbt Core only has a local CLI.
2. **Snowflake semantic views:** native, free, queryable from Streamlit and the agent, and governed by Snowflake RBAC.

**How the agent queries it**
1. **Free-form text-to-SQL on raw tables:** flexible, but error-prone and risky.
2. **Tool calling:** the LLM fills `{metric, dimensions, filters, time_range}`, validated against `metrics.yml`; Python compiles deterministic SQL.
3. **Governed text-to-SQL:** the LLM writes SQL, restricted to semantic views and validated before execution.
4. **Snowflake Cortex Analyst:** managed, but hides the mechanics.

## Decision
- Semantic layer: **Snowflake semantic views** (plus `metrics.yml` as the tool schema and validator allow-list).
- Agent SQL: **two modes**.
  - **Default: tool calling** (option 2).
  - **Advanced: governed text-to-SQL** (option 3). `sqlglot` enforces a single `SELECT`, `SEMANTIC.*` objects only, no DDL/DML, and a row limit.
- Both modes execute **under the end user's role**.

## Consequences
- Metric definitions are the same in dashboards and in the AI.
- The tool-calling compiler is unit-testable. The text-to-SQL mode shows flexibility and how to make it safe.
- The eval harness measures accuracy of both modes on the same golden set.
- Out-of-catalogue questions get "I can't answer that from governed metrics" rather than a guess.
- MetricFlow and Cortex Analyst remain stretch comparisons.
