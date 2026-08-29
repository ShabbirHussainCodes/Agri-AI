# Deployment & Environment

> Free-tier, India-first. Numbers below are August 2026 and change often — re-verify before relying on them, and cite a dated console screenshot in ADRs rather than a public docs number.

## Topology

| Piece | Where | Notes |
|---|---|---|
| Frontend (Next.js PWA) | Vercel Hobby | non-commercial clause is fine for a portfolio project |
| AI backend (FastAPI + ML) | HF Spaces (16 GB RAM free) **or** Cloud Run `asia-south1` | HF for zero-card; Cloud Run for Docker/GCP learning + Mumbai locality (needs a card) |
| DB + auth + vector + storage | Supabase, project `agriai-db`, `ap-south-1` | free tier; see limits below |
| Scheduling | GitHub Actions cron + Supabase Cron | one GH job doubles as the Supabase keep-alive |
| Observability | Langfuse Cloud Hobby | OpenTelemetry-instrumented |

## Supabase free-tier facts to design around

- 500 MB DB, 1 GB storage, 5 GB egress (+5 GB cached, shared with API responses), 500 MB RAM shared CPU, 50,000 auth MAU.
- **Paused after 1 week of inactivity** → a daily keep-alive cron is required, and must run in the week before any demo.
- **"Limit of 2 active projects"** — BillingMars already uses one slot. ⚠️ Not documented whether this is per-org or per-account; **check the dashboard before creating `agriai-db`.** If per-org, a new free org frees BillingMars' slot.

## Containers

One `Dockerfile` for the Python service (pin `python:3.12-slim`, install ML system libs explicitly). One `docker-compose.yml` for local Postgres+pgvector. Do **not** containerise the Next.js frontend (Vercel builds it natively).

## Environment configuration

All config via `AGRIAI_*` env vars (see `.env.example`). Local dev uses `AGRIAI_LOCAL_DATABASE_URL` (docker-compose Postgres) so it never touches the single free Supabase project. Production secrets are set in the hosting platform's env settings, never committed.

## Demo-day checklist

- Wake the HF Space ~10 min before presenting (free CPU Spaces sleep).
- Confirm the Supabase project is not paused (keep-alive running).
- Have the fallback LLM provider configured and a pre-warmed cache path — Groq free-tier TPM is thin for rapid back-to-back questions.
- The vision model is Preview status — test it the morning of, keep a fallback.
