# AgriAI web app

Next.js (App Router) PWA. **UI only**: no AI logic here, every answer comes from the FastAPI
backend (`apps/api`). Decisions: `docs/decisions/ADR-0017-web-app-and-deployment.md`.

> This is a recent Next.js (16.x). Before changing framework-level code read the matching guide in
> `node_modules/next/dist/docs/` (see `AGENTS.md`).

## Run it locally
```bash
cd apps/web
cp .env.example .env.local        # then put the anon key from `supabase status` in it
npm install
npm run dev                       # http://localhost:3000
```
The API must be running (`uvicorn` in `apps/api`) and its `AGRIAI_WEB_BASE_URL` must be the URL the
browser uses (default `http://localhost:3000`), otherwise the browser blocks the calls (CORS).

`NEXT_PUBLIC_*` values are inlined **at build time** and are public. Only the anon (publishable)
key belongs there, never a service-role key.

## Checks
```bash
npm run lint
npm run typecheck
npm run gen:types   # regenerate lib/api-types.ts from openapi.json (see below)
npm run test:e2e    # builds, serves, runs Playwright against a STUBBED API (no DB, no LLM)
```
The e2e tests use Playwright's Chromium; if it is not installed where Playwright expects, set
`PLAYWRIGHT_CHROMIUM_PATH` to a Chromium binary. Screenshots land in `test-results/screens/`.

## API types
`lib/api-types.ts` is generated from `openapi.json`, which is generated from the backend:
```bash
cd apps/api && python -m scripts.dump_openapi > ../web/openapi.json   # backend changed
cd ../web && npm run gen:types
```
`apps/api/tests/test_openapi_contract.py` fails if `openapi.json` no longer matches the backend.

## What v0 does not have
Voice, photo diagnosis, market prices, push notifications, offline use (no service worker). It
ships a web manifest, but whether a phone offers "install" is **not verified** yet: check on a
real Android phone over HTTPS. Hindi text has had no native-speaker review.

## Deployed (Vercel)
Root Directory `apps/web`, branch `main`. Environment variables are set in the Vercel project (Settings →
Environment Variables), never in Git: `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_SUPABASE_URL`,
`NEXT_PUBLIC_SUPABASE_ANON_KEY`. They are read at build time, so changing one needs a redeploy. The API
allows exactly one browser origin (its `AGRIAI_WEB_BASE_URL`), so a new web domain needs that updated too.
