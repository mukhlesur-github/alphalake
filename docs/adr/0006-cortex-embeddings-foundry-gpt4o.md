# ADR-0006: Cortex for embeddings and search, GPT-4o on Foundry for generation

- **Status:** Accepted
- **Date:** 2026-11-18

## Context
RAG needs an embedding model, a vector index, and a generation LLM. We already have **GPT-4o deployed on Microsoft Foundry** (API key). GPT-4o is a chat model, so it can't produce embeddings.

## Options considered
1. **All Cortex** (`EMBED_TEXT`, Cortex Search, `COMPLETE`): data never leaves Snowflake, but we wouldn't use the existing Foundry deployment.
2. **Cortex embeddings + search, GPT-4o (Foundry) generation:** embeddings live next to the data, and generation uses a strong existing model.
3. **External embeddings (e.g., a Foundry embedding deployment) + external vector DB:** more moving parts and more data movement.

## Decision
Option 2:
- Embeddings: `SNOWFLAKE.CORTEX.EMBED_TEXT_1024('snowflake-arctic-embed-l-v2.0', …)` stored as `VECTOR(FLOAT, 1024)`
- Retrieval: Cortex Search service (hybrid), plus manual `VECTOR_COSINE_SIMILARITY` for learning
- Generation and routing: GPT-4o on Foundry via `langchain-openai` `AzureChatOpenAI` inside the LangGraph agent (ADR-0011), API key from env or secret

Everything goes through `LLMProvider` / `EmbeddingProvider` interfaces, with Cortex `COMPLETE` available as an alternative provider.

## Consequences
- Retrieved chunks and metric results are sent to Azure for generation. That's acceptable for synthetic data; in a real firm this would need a data-classification review. (PII is redacted before embedding anyway.)
- Calling Foundry from Streamlit in Snowflake requires an external access integration and a network rule.
- Embedding model choice is fixed per index. Changing models means re-embedding everything, so the model name is stored on every chunk.
- The eval harness can compare GPT-4o against Cortex `COMPLETE` on the same golden set.
