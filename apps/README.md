# apps/

Application code (created during implementation phases — empty for now).

- **`api/`** — Python FastAPI backend (the AI backend). Module layout and rules: `docs/backend/backend-architecture.md`. Routers hold no business logic.
- **`web/`** — Next.js (App Router) PWA. UI only, no AI/business logic. See `docs/frontend/frontend-architecture.md`.

Do **not** put ingestion, evals, migrations, or reference data here — they have their own top-level folders.
