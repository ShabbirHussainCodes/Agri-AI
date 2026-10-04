# ADR-0017: Web app v0 (client-side Next.js calling FastAPI directly), per-user and global /ask caps, and the free-tier deployment topology

- **Status:** Accepted
- **Date:** 2026-10-05
- **Deciders:** Shabbir (approved the UI proposal U1–U6 on 2026-10-04; delegated the remaining choices) + Claude as advisor
- **Implements:** ADR-0001 (Next.js PWA, UI only). Relies on ADR-0003 (RLS is the gatekeeper) and ADR-0009 (own Supabase project).

## Context
Phases 1–6 produced a backend with no way for a farmer to use it. The primary user is on one shared low-end Android phone with intermittent data, more comfortable with Hindi than English. The binding resource constraint is the Groq free tier: about 40 `/ask` calls a day for the whole project (CLAUDE.md section 11). Signup is open, so one curious visitor could use the day's budget.

## Decisions
1. **v0 scope (what a farmer can do):** sign up / log in; add a farm (GPS or typed latitude/longitude, three big soil buttons in the farmer's own words: retili / domat / chikni, one crop and its sowing date); see the farm **diary** (activities and saved questions with their answers, newest first); ask a question; log "I irrigated today" in two taps with a confirmation (rule 8: nothing is written before the farmer confirms); edit soil and location. Hindi by default, English one tap away. **Not in v0:** voice, photo diagnosis, market prices, push notifications, offline use.
2. **Mostly client components; the browser calls FastAPI directly** with the Supabase JWT in the `Authorization` header. Rejected: server components or a Next.js proxy layer. They would need cookie-based Supabase SSR auth and would put a second server in front of the real one, for no benefit to a page whose content is per-user and uncacheable. `supabase-js` is used for authentication only; all data goes through FastAPI, so the JWT, RLS and the safety layers apply to every read and write (ADR-0003).
3. **CORS allowlist** (`AGRIAI_WEB_BASE_URL` plus `AGRIAI_CORS_EXTRA_ORIGINS`), methods GET/POST/PATCH, headers Authorization/Content-Type, **no credentials**: the token is not a cookie, so there is nothing for a cross-site request to ride on.
4. **Types are generated, not hand-written.** `apps/web/openapi.json` is dumped from the FastAPI app (`apps/api/scripts/dump_openapi.py`), `openapi-typescript` turns it into `lib/api-types.ts`, and `tests/test_openapi_contract.py` fails if the committed file no longer matches the backend (compared structurally: routes, schema properties, required fields), so the browser cannot drift from the API silently.
5. **Every answer is saved** to a new `advisories` table (`20261005120000_advisories.sql`: RLS on farm ownership, select and insert only for `authenticated`), which is what makes the diary possible and gives each answer an audit trail. `GET /farms/{id}/advisories` returns them. The stored `response` is kept as JSON so an old row never fails to load after the response schema grows.
6. **Caps on `/ask`:** 10 per user and 35 across everyone per rolling 24 hours (settings `AGRIAI_ASK_LIMIT_PER_USER_PER_DAY` / `..._GLOBAL_PER_DAY`, 0 = off). Counted from the saved advisories through a `security definer` function (`asks_in_last_day()`), because RLS would otherwise hide other users' rows from the global count. Over the limit: HTTP 429 `ask_limit_reached` with a bilingual message and `scope` user or global, **before** any LLM call, so a refused call costs nothing. 35 is deliberately under the ~40/day the measured budget allows, leaving room for the owner's own testing. Tradeoff: only answers that were produced are saved (abstentions included), so a call that fails part-way (provider error) is not counted although it may already have spent tokens. A user who keeps triggering such failures could spend budget without hitting their own cap; the global cap does not see it either. Not measured; revisit with real usage.
7. **The browser renders each evidence type visibly differently** (rule 3): the advice first; "calculated by AgriAI" (the water balance, with the Open-Meteo credit that CC BY 4.0 requires); the pesticide label card (only on an answer, never on an abstention, always with the "the pack label is the legal source" line); "what the documents say" (quotes, with source, marked as not AgriAI-verified); the model's reasoning, collapsed. Abstention is a calm sky-blue card, not an error.
8. **Backend messages are bilingual in one string** (Hindi paragraph, blank line, English paragraph). The browser shows the half matching the chosen language (`lib/text.ts`); anything else is shown whole.
9. **Deployment topology (free tier):** web on Vercel Hobby; API as a Docker image on a Hugging Face Space (`apps/api/Dockerfile`, bundled by `deploy/hf-space/make_bundle.py`; embedding model baked into the image); database/auth on Supabase `agriai-db`; a daily GitHub Actions call to `/health/db` keeps Supabase from pausing and wakes the Space. Cloud Run in `asia-south1` stays the alternative if the Space proves too slow or too unstable. Runbook: `docs/deployment/deployment.md`.

## Consequences
- **Positive:** a real farmer-facing surface that demonstrates the two differentiators (a per-farm record that persists, and answers that separate their evidence); the free-tier LLM budget is protected in code, not by hope; the contract between browser and API is checked by a test.
- **Not verified, and stated so nobody assumes otherwise:**
  - The Dockerfile, the HF bundle and both GitHub workflows have **not been run** (the session that wrote them had no Docker and no GitHub Actions). The first deploy is their first test.
  - Supabase connection details for a hosted deployment (which pooler/port, IPv4 reachability from the host, and whether the project's JWTs are asymmetric so the JWKS URL returns keys) must be checked in the Supabase dashboard; they are listed in the runbook rather than asserted.
  - PWA "install" is not verified on a real phone; there is no service worker, so no offline use.
  - Hindi strings have had no native-speaker review (CLAUDE.md section 6).
  - `tests/test_advisories_db.py` needs a database and has not been run in the session that wrote it.
  - A real browser on a low-end phone was not tested; the e2e tests run Chromium at phone width against a stubbed API.
- **Cold start:** a sleeping free Space takes time to wake and the first request may fail or be slow; the app shows a "could not reach the server" message in that case. The keep-alive reduces, not removes, this.
- **Open signup** is kept with the cap as the guard. If abuse appears, switch signup to email confirmation (CLAUDE.md section 11) or invite-only.

## Verification
12 Playwright tests (`apps/web/tests/app.spec.ts`) on the production build against a stubbed API and session: login and language toggle, onboarding (including a rejected half-typed location), asking in both languages, all evidence types, abstention without label card, daily limit, unreachable server, irrigation log with confirmation, profile completion, no horizontal scroll. Backend: `tests/test_ask_cap.py` (cap logic and 429), `tests/test_openapi_contract.py`.

## Links
ADR-0001, ADR-0003, ADR-0009, ADR-0015, ADR-0016, `apps/web/README.md`, `docs/deployment/deployment.md`.
