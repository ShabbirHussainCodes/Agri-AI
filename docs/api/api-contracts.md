# API Contracts

> FastAPI. One Pydantic model serves triple duty (LLM schema · response model · OpenAPI). These are the *proposed* Phase-1+ contracts; keep them in sync with implementation. Auth: Supabase-issued JWT, verified server-side against the project JWKS. All routes require auth unless noted.

## Conventions

- Base path `/api/v1`. JSON. Errors: `{ "error": { "code", "message", "field?" } }` with a helpful, non-vague message.
- `routers/` contain no business logic — they validate, call a `service`, and return.
- Timestamps ISO-8601 UTC. IDs are UUIDs.

## Auth

Handled by Supabase Auth on the client; the backend only **verifies** the JWT (JWKS, RS256, check `aud`/`exp`, extract `sub` → profile). We write the verification middleware ourselves (learning value); we do not roll our own token issuance.

## Farm & onboarding

| Method | Path | Body → Response |
|---|---|---|
| POST | `/farms` | `{name, lat, lon, area_ha, district?, state?}` → `Farm` |
| GET | `/farms` | → `Farm[]` (only the caller's) |
| GET | `/farms/{id}` | → `Farm` |
| POST | `/farms/{id}/crops` | `{crop_id, variety, sowing_date}` → `FarmCrop` (stage computed) |
| GET | `/farms/{id}/timeline` | → chronological `activities` + `advisories` + `disease_scans` |

## Activities (write → confirmation required)

| Method | Path | Notes |
|---|---|---|
| POST | `/farms/{id}/activities` | `{type, occurred_on, details}` → `Activity`. When proposed by the agent, requires explicit user confirmation before this is called. |

## Ask (the agent)

| Method | Path | Body → Response |
|---|---|---|
| POST | `/farms/{id}/ask` | `{question, language?}` → `AdvisoryResponse` |

`AdvisoryResponse` (evidence-typed):
```
{
  structured_data: {...},
  live_data: {...} | null,
  retrieved_evidence: [ { source_org, doc_title, published_year, page, quote } ],
  model_inference: string,
  recommendation: string,
  confidence: number | null,
  abstained: boolean,
  abstained_because: string | null,
  citations_valid: boolean
}
```

## Voice

| Method | Path | Notes |
|---|---|---|
| POST | `/speech/transcribe` | multipart audio → `{transcript, language, low_confidence}`. The client always shows the editable transcript before sending it to `/ask`. |

## Crop image diagnosis

| Method | Path | Notes |
|---|---|---|
| POST | `/farms/{id}/scans` | multipart image → runs quality gate → classifier → VLM → RAG → safety layer. Returns `DiagnosisResponse` (top-3 + calibrated bands + "model saw" vs "label says" + sources + abstention). Rejected early with a clear "take a better photo" message if the quality gate fails. |
| POST | `/scans/{id}/feedback` | `{confirmed_label?}` → records farmer feedback (future field dataset) |

## Market (modular, secondary)

| Method | Path | Notes |
|---|---|---|
| GET | `/market/advice` | `?commodity=&district=&days=` → `{series, percentile_band, signal, explanation, disclaimer}`. Statistics in code; LLM only explains. Never blocks core routes. |

## Reminders & push

| Method | Path | Notes |
|---|---|---|
| POST | `/farms/{id}/reminders` | write → confirmation required |
| POST | `/push/subscribe` | store Web Push subscription |

## Validation & limits

Every input is Pydantic-validated. Uploads: size + MIME + image-decode check + server-side resize before anything else. Per-user rate limiting on `/ask`, `/scans`, `/speech`. See `docs/security/security-model.md`.
