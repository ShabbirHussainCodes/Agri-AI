# ADR-0003: RAG on pgvector inside Supabase

- **Status:** Accepted
- **Date:** 2026-08-27
- **Deciders:** Shabbir (+ Claude)

## Context
AgriAI needs vector retrieval over ~a few thousand–15k agricultural chunks, filtered by the farmer's crop/state/stage, alongside relational farm data, on a free tier.

## Options considered
- **pgvector in the same Supabase Postgres** — one database; metadata filter is a plain SQL join with real FK columns; transactional consistency; one access-control story.
- **Dedicated vector DB (Qdrant/Weaviate/Pinecone/Upstash)** — good hybrid features, but a second stateful system to keep in sync with relational data; unjustified at this scale.

## Decision
pgvector inside the AgriAI Supabase Postgres. Embeddings: local ONNX `multilingual-e5-small` (v1, 384-d) → `BAAI/bge-m3` (v2, 1024-d). Reranker: `bge-reranker-v2-m3` (ONNX, top-20). Hybrid dense + full-text with RRF.

## Why
1k–15k chunks is three orders of magnitude below where a dedicated vector DB matters. Filtering by the farm's actual crop/district becomes a joinable `WHERE`, which is exactly AgriAI's context-aware retrieval need. Groq has no embeddings endpoint and HF Inference free credits are negligible, so embeddings run locally on CPU.

## Consequences
- **Positive:** one system, one backup story, real metadata filtering, RLS-aligned access.
- **Trade-off:** Postgres has no Hindi stemmer (mitigations in `rag-design.md`); reranker CPU latency is unverified and must be measured; free-tier 500 MB RAM caps corpus size and drives the embedding-dimension choice.
- **Follow-up:** Qdrant is the sanctioned second choice if bge-m3's sparse/ColBERT modes are ever needed.

## Links
`docs/rag/rag-design.md`, `docs/database/schema.md`.
