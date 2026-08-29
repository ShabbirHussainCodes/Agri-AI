# System Architecture

> Read `CLAUDE.md` first. This document is the top-level map; deeper detail lives in the sibling `docs/` areas and the ADRs.

## 1. The one-paragraph version

A Next.js PWA on the farmer's phone talks over HTTPS to a Python FastAPI backend. The backend holds the **agent core** (a hand-rolled tool-calling loop), the **RAG pipeline**, the **vision pipeline**, the **speech pipeline**, and — critically — a **deterministic safety layer that runs after the LLM**. Tools read from a single Supabase Postgres database (farm data + activity history + `pgvector` chunks + the agrochemical label table + a price time-series), from external APIs (weather, mandi prices, soil), and from AI providers (Groq for text/vision/speech; local ONNX for embeddings and reranking). Crop photos live in Supabase Storage behind a `StorageProvider` interface. Scheduled jobs (GitHub Actions cron + Supabase Cron) call the backend the same way a user would.

## 2. Layers

```
CLIENT        Next.js PWA · MediaRecorder voice · camera · Web Push · farm timeline · offline shell
   │ HTTPS
API/APP       FastAPI · JWT verify (JWKS) · Pydantic validation · rate limit · upload scan+resize
   │            · domain services · OpenTelemetry
AGENT/AI      tool loop (hand-rolled) · RAG pipeline · vision pipeline · speech pipeline
   │            · [DETERMINISTIC SAFETY LAYER]
   │            · provider abstraction → Groq · local ONNX · Mistral (fallback)
DATA          Postgres (farm + activity) · pgvector (chunks) · agrochemical label table
   │            · price time-series · Supabase Storage (photos)
PLATFORM      Supabase (Mumbai) · HF Spaces / Cloud Run · Vercel · GitHub Actions · Langfuse · Sentry
```

## 3. Why one backend, not microservices

Solo project. A single FastAPI service with clear internal module boundaries (`agent/`, `rag/`, `vision/`, `speech/`, `safety/`, `providers/`, `integrations/`) gives all the separation we need without network hops that only make debugging harder. The one deliberate split is **ingestion**: `ingest/` runs on the developer laptop (Docling needs ~6 GB RAM and it is a one-time offline job), never in the production container.

## 4. The two-call request shape (a hard provider constraint turned into a feature)

Groq cannot combine strict structured output with tool use or streaming in one call. So a request runs in two turns:

- **Turn A — evidence gathering:** the streaming tool loop calls read tools (`get_farm_context`, `get_weather`, `search_knowledge`, `lookup_agrochemical`, …) and assembles an evidence bundle.
- **Turn B — answer construction:** a separate call with no tools and a strict JSON schema emits the evidence-typed response object.

This split is *where provenance and confidence get attached*, and it naturally enforces the "prediction vs evidence vs structured data vs recommendation" separation. Detail: `docs/ai/ai-architecture.md`.

## 5. The safety gate sits after the model

Every advisory output passes through the deterministic safety layer **after** generation: banned-molecule denylist, dose + waiting-period lookup from the version-stamped table, citation-existence check, and the retrieval confidence floor. Because it runs last, no LLM output and no prompt-injected corpus text can bypass it. Detail: `docs/security/security-model.md` and `docs/ai/agent-design.md`.

## 6. Region as data, not code

Region is a `knowledge_pack` concern: corpus + crop calendar + agrochemical label table + language set + weather/price adapters. Only the India pack is built. The seams exist so a second pack is possible later; they are not abstracted ahead of a second concrete implementation.

## 7. Cross-references

| Concern | Document |
|---|---|
| AI / two-call flow / providers | `docs/ai/ai-architecture.md` |
| Agent tools & determinism boundary | `docs/ai/agent-design.md` |
| Vision pipeline | `docs/ai/multimodal-vision.md` |
| RAG | `docs/rag/rag-design.md` |
| Data model | `docs/database/schema.md` |
| API surface | `docs/api/api-contracts.md` |
| Frontend | `docs/frontend/frontend-architecture.md` |
| Backend module layout | `docs/backend/backend-architecture.md` |
| External APIs | `docs/integrations/external-integrations.md` |
| Security & privacy | `docs/security/security-model.md` |
| Deployment | `docs/deployment/deployment.md` |
| Testing | `docs/testing/testing-strategy.md` |
| Observability | `docs/observability/observability.md` |
| Decisions | `docs/decisions/` |
| Diagrams | `docs/architecture/diagrams.md` |
