# Security & Privacy Model

> Designed in from the start. Several items here are also correctness/safety properties, not just hardening.

## 1. Secrets

- Never in source, Git, docs, or the frontend bundle. Environment variables only, namespaced `AGRIAI_*`.
- `.env.example` holds placeholders only. The Supabase **service-role key is server-only** and never reaches the browser (the browser uses the anon key with RLS).

## 2. Supabase project isolation

AgriAI uses its own Supabase project `agriai-db` with its own database, pgvector, auth, storage, and keys. The separate **BillingMars** project is never read, modified, migrated, or shared. (ADR-0009.)

## 3. Authentication & authorization

- Supabase Auth issues JWTs; the backend **verifies** them (JWKS, RS256, `aud`/`exp`, `sub` → profile). We write the verification middleware ourselves; we do not roll our own issuance/session/refresh logic.
- **Row-Level Security** on every user-owned table: a row is visible/writable only to its owning `auth.uid()`. Storage bucket `crop-photos` uses the same policy.

## 4. Farmer-data privacy

- Farm location, crop condition, and photos are **personal/confidential data**.
- **Vision provider = Groq** specifically because its Services Agreement §4.2 prohibits training on Inputs/Outputs by default, treats Customer Data as confidential, and its DPA processes only on documented instructions. **Never route farmer photos through a provider whose free tier trains on inputs or allows human review** (why Gemini free tier was rejected — ADR-0004).
- Geocode once and store; don't hold real-time location.
- Collect minimal PII.

## 5. Input validation & uploads

- Every input Pydantic-validated.
- Uploads: size cap + MIME check + actual image-decode + server-side resize before any processing. Reject non-images early.

## 6. Rate limiting

Per-user limits on `/ask`, `/scans`, `/speech` — protects the free-tier provider budget and blunts abuse.

## 7. AI-specific security

- **Deterministic safety layer runs after the LLM.** Banned-molecule denylist + dose/waiting-period lookup + citation validation + retrieval floor. No LLM output and no injected corpus text can bypass it.
- **Prompt injection:** retrieved corpus text is untrusted — delimited, never able to trigger tools; injection cases are in the eval set.
- **The LLM never emits a pesticide dose.** Doses come only from the version-stamped `agrochemicals` table (ADR-0005).
- **Malicious documents:** ingestion parses on the laptop, not in production; parsed text is treated as data, not instructions.
- **Write tools require explicit user confirmation.**

## 8. What we do not claim

We do not claim regulatory approval or medical/agronomic authority. Advisory outputs carry appropriate framing, and safety-critical facts are always traceable to a dated, cited source or the system abstains.
