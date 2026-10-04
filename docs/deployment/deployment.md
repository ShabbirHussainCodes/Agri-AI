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
- **"Limit of 2 active projects"** — confirmed **per account, across all orgs** (2026-08-29, verified against the live Supabase account). `agriai-db` + `billingmars-db` now use both free slots; a third project needs pausing, upgrading, or deleting one of them.

## Containers

One `Dockerfile` for the Python service (pin `python:3.12-slim`, install ML system libs explicitly). One `docker-compose.yml` for local Postgres+pgvector. Do **not** containerise the Next.js frontend (Vercel builds it natively).

## Environment configuration

All config via `AGRIAI_*` env vars (see `.env.example`). Local dev uses `AGRIAI_LOCAL_DATABASE_URL` (docker-compose Postgres) so it never touches the single free Supabase project. Production secrets are set in the hosting platform's env settings, never committed.

## Demo-day checklist

- Wake the HF Space ~10 min before presenting (free CPU Spaces sleep).
- Confirm the Supabase project is not paused (keep-alive running).
- Have the fallback LLM provider configured and a pre-warmed cache path — Groq free-tier TPM is thin for rapid back-to-back questions.
- The vision model is Preview status — test it the morning of, keep a fallback.

## Deploying v0 step by step (ADR-0017)

Written 2026-10-05 from the repository, **not yet carried out**: nothing below has been run against real
accounts. Where a dashboard detail could not be checked from the repo it says **verify**. Secrets go only
into the platform's own settings pages, never into Git, chat or a file in this repo.

### 1. Supabase `agriai-db` (remote)
1. In the Supabase dashboard of `agriai-db` (not BillingMars), note the project ref, the anon key
   (Project Settings → API) and the database password.
2. From the repo root on your machine: `supabase link --project-ref <ref>`, then `supabase db push`
   (applies everything in `supabase/migrations/`, including `20260930120000`, `20261004120000`,
   `20261005120000`). Never `db reset` against anything with data.
3. **Verify the JWT signing keys:** open `https://<ref>.supabase.co/auth/v1/.well-known/jwks.json` in a
   browser. If it lists keys, `AGRIAI_JWKS_URL` is that URL. If the list is empty, the project signs with
   the legacy shared secret and the API cannot verify tokens: switch the project to the asymmetric
   signing keys in the dashboard first.
4. **Database URL:** Dashboard → Connect. The direct host may be IPv6-only on the free plan, and a free
   Hugging Face Space may not reach IPv6 (**verify**). If so use the **session-mode pooler** string (it
   serves IPv4 and, unlike transaction mode, keeps prepared statements and `SET LOCAL ROLE` working with
   asyncpg). Use that as `AGRIAI_DATABASE_URL`.
5. Auth → Providers → Email: decide confirmation. v0 works either way; "Confirm email" off is simplest
   but allows throwaway signups (the `/ask` caps are the guard).
6. **Ingest the corpus into agriai-db** from your laptop (113 chunks; `ingest/README.md`) pointing the
   ingest job's database URL at the remote project. Without it `/ask` has nothing to retrieve.

### 2. API on a Hugging Face Space
1. Create a **Docker** Space (can be private or public; the API is reachable either way).
2. `python deploy/hf-space/make_bundle.py <path-to-your-clone-of-the-space>`, then in that folder
   `git add -A && git commit -m deploy && git push`. Re-run it whenever `data/` (crop table, denylist,
   label table) or the API changes.
3. Space → Settings → Variables and secrets. **Secrets:** `AGRIAI_DATABASE_URL`, `AGRIAI_GROQ_API_KEY`.
   **Variables:** `AGRIAI_JWKS_URL`, `AGRIAI_WEB_BASE_URL` (the Vercel URL, exactly, no trailing slash),
   `AGRIAI_ENV=production`. The caps default to 10 per user and 35 global per day.
4. The first build downloads a ~470 MB model into the image; read the build log. Open
   `https://<space>.hf.space/health` and then `/health/db` (should show `crops_seeded`).

### 3. Web on Vercel
1. Import the GitHub repo, **Root Directory = `apps/web`**.
2. Environment variables (they are inlined at build time and are public, so only these three):
   `NEXT_PUBLIC_API_BASE_URL` (the Space URL), `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   (anon/publishable key only, never the service-role key).
3. Deploy, then put the resulting URL in the Space's `AGRIAI_WEB_BASE_URL` (a preview URL can go in
   `AGRIAI_CORS_EXTRA_ORIGINS` as a JSON list). A CORS error in the browser console means these two differ.

### 4. Keep-alive
GitHub → Settings → Secrets and variables → Actions → **Variables**: `AGRIAI_API_URL` = the Space URL.
Run the `keepalive` workflow once by hand (Actions tab → Run workflow) and confirm it is green.

### 5. Smoke test on a real phone
Sign up, add a farm with a location and soil, ask "क्या आज सिंचाई करूँ?" (expect "cannot assess" until the crop
table is verified, see CLAUDE.md section 11), log an irrigation, reload and see the diary. Check whether the
browser offers "Add to Home screen" (not verified yet).

### What still limits a real-farmer launch
The crop/soil table and the CIB&RC data files are unverified (irrigation answers `cannot_assess` and no
pesticide label card can appear), Hindi is unreviewed, and nothing from the research corpus is verified
advice (ADR-0012). Treat the deployment as a demo until those are done.
