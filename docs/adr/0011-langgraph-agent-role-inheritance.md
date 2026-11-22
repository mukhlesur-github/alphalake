# ADR-0011: LangGraph research agent that inherits the user's role

- **Status:** Accepted
- **Date:** 2026-11-18

## Context
The assistant must decide between structured (SQL) and unstructured (RAG) sources, or use both; verify its output; retry within limits; and never expose data the user isn't entitled to.

## Options considered
**Framework**
1. **Plain Python router:** minimal dependencies and full control, but we'd hand-roll state, branching, and retries.
2. **LangGraph:** explicit state graph with conditional edges, retries, and checkpointing. Widely used and in demand.
3. **Managed agent frameworks:** less to learn about the mechanics.

**Data access identity**
1. **One privileged app role:** simple, but the AI can see more than the user. That's a governance failure.
2. **Run queries under the user's persona role:** masking, row access, and document tiers apply automatically.

## Decision
- **LangGraph** state graph: input guardrails → router → {metric tool, RAG tool} → synthesis → output checks (at most 2 retries).
- GPT-4o through `langchain-openai` `AzureChatOpenAI` (Foundry endpoint, API key), behind our `LLMProvider` abstraction.
- The app authenticates as `SVC_APP` and runs every agent query under the **signed-in persona's role** (`USE ROLE`, secondary roles off). RAG adds a mandatory `access_tier` pre-filter derived from the same role.
- Every answer returns page citations, SQL lineage (SQL, semantic view, role), and the route.

## Consequences
- `SVC_APP` must be granted the persona roles, and the app must never fall back to a privileged role. Tests verify this.
- LangGraph adds a dependency. Tool and guardrail logic stay in plain, framework-independent Python modules, so it's easy to unit-test and to swap frameworks.
- Streamlit in Snowflake needs its own role-inheritance approach, which is evaluated in Phase 8.
