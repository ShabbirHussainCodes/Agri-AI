# Security & Privacy Model

> Designed in from the start. Several items here are also correctness/safety properties, not just hardening.

## 1. Secrets

- Never in source, Git, docs, or the frontend bundle. Environment variables only, namespaced `AGRIAI_*`.
- `.env.example` holds placeholders only. The Supabase **service-role key is server-only** and never reaches the browser (the browser uses the anon key with RLS).

## 2. Supabase project isolation

AgriAI uses its own Supabase project `agriai-db` with its own database, pgvector, auth, storage, and keys. The separate **BillingMars** project is never read, modified, migrated, or shared. (ADR-0009.)

## 3. Authentication & authorization

- Supabase Auth issues JWTs; the backend **verifies** them (JWKS, ES256, `aud`/`exp`, `sub` → profile). We write the verification middleware ourselves; we do not roll our own issuance/session/refresh logic.
- **Row-Level Security** on every user-owned table: a row is visible/writable only to its owning `auth.uid()`. Storage bucket `crop-photos` uses the same policy.

## 4. Farmer-data privacy

- Farm location, crop condition, and photos are **personal/confidential data**.
- **Vision provider = Groq** specifically because its Services Agreement §4.2 prohibits training on Inputs/Outputs by default, treats Customer Data as confidential, and its DPA processes only on documented instructions. **Never route farmer photos through a provider whose free tier trains on inputs or allows human review** (why Gemini free tier was rejected — ADR-0004).
- Geocode once and store; don't hold real-time location.
- Collect minimal PII.

## 5. Input validation & uploads

- Every input Pydantic-validated.
- Uploads (built in Phase 7, `app/vision/imaging.py`, ADR-0018): 8 MB cap; the file type from the **magic bytes** (JPEG, PNG, WebP), never from the client's Content-Type or file name; the pixel count from the header before decoding (a 40 MP cap, so a small file cannot expand into gigabytes); a real decode; EXIF orientation applied and **all metadata dropped** by re-encoding (a phone photo carries GPS coordinates and a device id); downscale to 1024 px. Every later stage and the stored copy see only that re-encoded JPEG, never the original bytes. The web app also shrinks the photo on the phone first, for speed.

## 5b. Photos (Phase 7)

- A photo is stored only in the **private** `crop-photos` bucket (JPEG, 2 MiB), under `<farm_id>/<scan id>.jpg`. The bucket's row-level policy is the same ownership rule as the farm data and the API writes as the caller with their own JWT, so no server key can bypass it; there is no public URL, the app makes a one-hour signed URL with the farmer's session. Proven against the real Storage API: another farmer's token cannot write, sign or delete under my farm's folder (`tests/test_storage_supabase.py`). The farmer can delete a scan and its photo (`DELETE /scans/{id}`).
- A photo reaches the vision provider (Groq, ADR-0004) **only after** the local checks pass (quality gate, then the on-server classifier). A photo that will be refused anyway never leaves the server.
- The vision model's output is untrusted text about an untrusted photo (a photo can carry printed words). Crop, condition and plant part are forced into a closed vocabulary; its one free sentence is cut to 240 characters, stripped of control characters and passed through the dose and banned-molecule guards before the farmer sees it, and reaches the answer model only inside a delimited "data, not instructions" block. The prompt-injection-by-photo case is in the pipeline eval (`evals/vision/vpipeline.py`).

## 6. Rate limiting

Per-user limits on `/ask`, `/scans`, `/speech` — protects the free-tier provider budget and blunts abuse. Built so far: `/ask` (10 per user, 35 global a day, ADR-0017) and `/farms/{id}/scans` (5 per user, 12 global a day; a photo check also counts toward the shared 35, because both use the gpt-oss-120b budget). A photo the quality gate refuses costs nothing and is not counted; it is still not rate limited by IP (Phase 11).

## 7. AI-specific security

- **Deterministic safety layer runs after the LLM.** Banned-molecule denylist + dose/waiting-period lookup + citation validation + retrieval floor. No LLM output and no injected corpus text can bypass it.
- **Prompt injection:** retrieved corpus text is untrusted — delimited, never able to trigger tools; injection cases are in the eval set.
- **The LLM never emits a pesticide dose.** Doses come only from verified rows of the version-stamped agrochemical table, copied by code into a label card; the model never sees them (ADR-0005, ADR-0016). Backstops that run after the model: a dose / waiting-period guard (47 of 47 adversarial phrasings blocked, from 12 before Phase 6) with a grounded-number rule, and a banned-molecule denylist.
- **Malicious documents:** ingestion parses on the laptop, not in production; parsed text is treated as data, not instructions.
- **Write tools require explicit user confirmation.**

## 8. What we do not claim

We do not claim regulatory approval or medical/agronomic authority. Advisory outputs carry appropriate framing, and safety-critical facts are always traceable to a dated, cited source or the system abstains.
