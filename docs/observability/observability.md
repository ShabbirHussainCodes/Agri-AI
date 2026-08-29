# Observability

> Supabase log retention is ~1 day, so we ship our own tracing and error tracking. Instrument via OpenTelemetry so the backend can be swapped without rewriting instrumentation.

## LLM tracing — Langfuse (Cloud Hobby, OTel-instrumented)
Trace every agent turn: tool calls, retrieved chunks, the two-call flow, token usage, latency, and abstention events. This is what makes debugging tractable during a hackathon. Core is MIT, so self-hosting is an escape hatch. Instrument through OpenTelemetry (the emerging GenAI standard) rather than a vendor SDK.

## What to trace
- Turn A tool sequence and each tool's latency.
- Retrieval: query, filters/tier reached, candidates, rerank scores, final top-k, whether the confidence floor abstained.
- Turn B: schema-valid or not, citation-validation result.
- Safety layer: which check fired, abstain vs pass.
- Provider used and any fallback-ladder hop.

## Application monitoring (optional)
Sentry for errors/stack traces + release tracking; Better Stack heartbeats to detect a silently-dead cron job (exactly how the Supabase keep-alive failing would surface). Axiom for structured log search compensates for Supabase's 1-day retention.

## Metrics that matter for this product
- Abstention rate (a feature, watch it deliberately).
- Retrieval floor hit-rate.
- Citation-validation failure rate.
- Free-tier token budget consumption vs the rate-limit ceiling.
- ASR low-confidence / transcript-edit rate.

## Privacy
Traces may contain farmer content — treat the tracing backend as holding personal data, keep it access-controlled, and don't log secrets. Prefer self-host if farmer content volume grows.
