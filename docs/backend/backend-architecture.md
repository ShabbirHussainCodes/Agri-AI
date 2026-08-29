# Backend Architecture

> Python 3.12 + FastAPI. One service, clear internal boundaries. Ingestion is a separate laptop-only job.

## Module layout (`apps/api/app/`)

```
main.py          app wiring
routers/         HTTP endpoints only — validate, call a service, return. NO business logic.
schemas/         Pydantic models: LLM schema + API response + OpenAPI contract (one source)
services/        domain logic: farms, activities, advisories, market
agent/           tool loop, tool definitions, versioned prompts
rag/             retrieval, RRF fusion, reranking, citation validation
vision/          quality gate, classifier, OOD, VLM adapter
speech/          STT/TTS adapters
safety/          banned-molecule denylist, dose lookup, abstention rules  (runs LAST)
providers/       LLMProvider / VisionProvider / SpeechProvider / EmbeddingProvider / RerankProvider
integrations/    open-meteo, data.gov.in, soilgrids, nominatim clients (typed, cached)
core/            config, auth (JWT verify), logging, otel, errors
```

## Design rules

- **Routers are thin.** All logic in `services/` and the pipeline modules, so it is unit-testable without HTTP.
- **The safety layer is a distinct module and always runs after the LLM step.** It is not a prompt instruction.
- **Providers are swappable.** Business logic never imports a vendor SDK directly — only the interfaces in `providers/`.
- **Deterministic helpers live in code, not prompts:** date/stage math, ET₀ balance, price statistics, citation checks.
- **Config via `core/config.py`** reads `AGRIAI_*` env vars (Pydantic Settings). No secrets in code.

## Error handling

Typed exceptions → consistent JSON error envelope with actionable messages. External API failures degrade gracefully (cached value, or an honest "weather unavailable right now" rather than a crash). AI provider failures fall through the provider ladder; if all fail, the endpoint returns an honest error, never a fabricated answer.

## Async & performance

Async I/O for provider and external-API calls. Aggressive caching for weather (per lat/lon/hour), geocoding (geocode once, store), and mandi ingest. Prompt caching (stable gpt-oss prefix) to stretch the free-tier token budget.

## Local dev

The **Supabase CLI local stack** (`supabase start`) provides Postgres + pgvector + Auth (`auth.uid()`, `auth.users`) locally, so development never touches the single free `agriai-db` project and RLS can be tested for real. `apps/api/.env`'s `AGRIAI_DATABASE_URL` points at it in dev (see ADR-0011).

## Ingestion (separate)

`ingest/` runs on the developer laptop (Docling ~6 GB RAM). It parses, contextualises, chunks, embeds, and upserts into the database. It is not part of the production container and has its own dependencies.
