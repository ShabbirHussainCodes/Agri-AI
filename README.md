# AgriAI

An AI-powered farming decision-support system for Indian smallholder farmers.

AgriAI keeps a **per-farm record** — crop, growth stage, soil, weather, and the farmer's own history of irrigation, fertiliser, spraying, and past problems — and reasons over that record to give **evidence-grounded, source-cited recommendations** in Hindi and English, through a text and voice interface. It is designed to be honest: it distinguishes what a model inferred from what a document actually says, and it says "I'm not sure" and points to a human expert when the evidence is weak.

> **Status:** Phase 0 — architecture and documentation. No application code yet. See [`docs/roadmap/roadmap.md`](docs/roadmap/roadmap.md).

---

## Why it exists

Useful farming information is fragmented, technical, rarely personalised to a farmer's actual situation, and almost never shows its source. India already has strong national digital-agriculture services; what we found missing in public-facing systems is **persistent per-farm state** and **source-attributed evidence** behind each recommendation. AgriAI is built around those two ideas, plus a hard rule that it never guesses anything with a safety consequence.

## What it does (target MVP)

- Onboard a farm in a couple of minutes, by voice if needed.
- Answer farming questions grounded in trusted agricultural knowledge, **with citations**.
- Turn real weather data (soil moisture, ET₀) into irrigation guidance.
- Analyse a crop photo honestly — top-3 candidates, calibrated uncertainty, and an explicit "not sure" path.
- Look up pesticide dose and waiting period **only** from a verified, version-stamped reference table — the AI never invents these.
- Record everything on the farm timeline so the next answer has context.

## Principles

- **Honesty over confidence.** Measured numbers, cited sources, and abstention when the evidence is thin.
- **Deterministic where it matters.** Anything with a safety or legal consequence (dose, banned molecules, dates) is code, not model output.
- **Free and open where practical.** Free tiers and open-source, chosen for real usefulness and learning value.
- **India-first, region-agnostic in structure.**

## Tech at a glance

Python + FastAPI · Next.js PWA · Supabase (Postgres + pgvector + auth + storage) · Groq (LLM + vision + speech) · local ONNX embeddings + reranker · Docling ingestion · Langfuse observability. Full rationale in [`docs/`](docs/) and the [ADRs](docs/decisions/).

## Documentation

Start with [`CLAUDE.md`](CLAUDE.md), then [`docs/roadmap/roadmap.md`](docs/roadmap/roadmap.md), then the relevant `docs/` area and [Architecture Decision Records](docs/decisions/).

## Setup

Environment configuration is documented in [`docs/deployment/deployment.md`](docs/deployment/deployment.md). Copy `.env.example` to `.env` and fill in your own credentials — never commit real secrets.

## Licence

TBD before first public release.
