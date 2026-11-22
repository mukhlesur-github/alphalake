# ADR-0010: Streamlit, local first, then Streamlit in Snowflake

- **Status:** Accepted
- **Date:** 2026-11-18

## Context
We need a UI for dashboards and the AI assistant, quick to build in Python.

## Options considered
1. **Local Streamlit:** fastest iteration and easy debugging, but runs only on your laptop.
2. **Streamlit in Snowflake (SiS):** hosted, governed by Snowflake RBAC, no server to run. Calling Foundry needs an external access integration, and package support is narrower.
3. **React + FastAPI:** more flexible, but much more work and off-topic for a data role.

## Decision
Build locally (Phase 7), then deploy the same app to SiS (Phase 8).

## Consequences
- App code must stay SiS-compatible: use packages available in the Snowflake Anaconda channel, and get the session via a helper that works both locally and in SiS.
- The Foundry API key is stored as a Snowflake `SECRET` for SiS.
