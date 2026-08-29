# ADR-0006: Evidence-typed response model

- **Status:** Accepted
- **Date:** 2026-08-27
- **Deciders:** Shabbir (+ Claude)

## Context
Trust requires the farmer to see the difference between "the model thinks" and "a document says" and "this sensor measured." A single opaque paragraph hides that difference.

## Decision
Every advisory is one structured object separating `structured_data`, `live_data`, `retrieved_evidence` (source + year + page + quote), `model_inference`, `recommendation`, `confidence`, `abstained` + `abstained_because`, and `citations_valid` (set by code). One Pydantic model = LLM schema + FastAPI response + OpenAPI. The UI renders the types distinctly.

## Why
The project principles demand separating prediction from evidence from structured data, and grounded reference material measurably improves answer quality. Structuring it makes provenance and abstention first-class, and the two-call flow (Turn A evidence → Turn B strict schema) gives a natural place to attach it.

## Consequences
- **Positive:** trust mechanism, not a disclaimer; contract-first; testable via schema assertions.
- **Trade-offs:** requires the two-call split (a Groq constraint anyway); the UI must design for multiple evidence types.

## Links
`docs/ai/ai-architecture.md`, `docs/api/api-contracts.md`.
