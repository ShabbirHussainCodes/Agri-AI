# CLAUDE.md — AgriAI

> Persistent context for any Claude (or human) session working on this repository.
> Read this **first**, then `docs/roadmap/roadmap.md`, then the relevant `docs/` and ADRs.
> Never assume the project is empty — check Git history and `docs/` before making changes.

---

## 1. What AgriAI is

AgriAI is an **AI-powered farming decision-support system for Indian smallholder farmers**.

It is **not** a generic chatbot. The product is a **stateful, per-farm agronomy record that reasons over that farm's own history and grounds every recommendation in cited evidence**. Chat (text + voice) is the *interface*; the *product* is the farm record + the evidence-grounded reasoning on top of it.

- **Primary user:** a smallholder farmer in India, on one shared low-end Android phone, intermittent data, often more comfortable with voice than typing. Farming is usually one income stream among several.
- **Region:** India-first. The architecture is **region-agnostic in structure** (region is a data/config concern — a "knowledge pack"), but only the India pack is built. Malaysia is **not** a product requirement and must not be highlighted.

### Differentiation (state it precisely — see §9 Claim discipline)
The public-facing systems we reviewed do not document **per-farm persistent state** or **source-attributed, evidence-grounded recommendations**. AgriAI's differentiation is exactly those two things, plus honest uncertainty (it can say "I'm not sure" and escalate).

---

## 2. Core problem

Useful farming information is fragmented, technical, not personalised to the farmer's actual situation, and rarely shows its source. AgriAI helps a farmer make better day-to-day decisions using: farmer/farm/crop profile, crop growth stage, soil, weather, activity history (irrigation/fertiliser/spray/sowing), crop images, trusted agricultural knowledge, and market prices — with clear separation between what the model inferred, what a document said, and what structured data measured.

---

## 3. Technology stack (locked — see ADRs)

| Layer | Choice | ADR |
|---|---|---|
| AI backend | Python 3.14 (3.12+) + FastAPI | ADR-0001, ADR-0011 |
| Frontend | Next.js (App Router) PWA — UI only | ADR-0001 |
| Agent | Hand-rolled tool-calling loop (Pydantic AI only later if a real need appears) | ADR-0002 |
| DB + auth + vector | Supabase Postgres + pgvector, **project `agriai-db`, region `ap-south-1` (Mumbai)** | ADR-0003, ADR-0009 |
| Text LLM | Groq `openai/gpt-oss-120b` (quality) + `gpt-oss-20b` (fast) | ADR-0004 |
| Vision | Groq `qwen/qwen3.6-27b` | ADR-0004 |
| Speech-to-text | Groq `whisper-large-v3-turbo` | — |
| TTS | Browser SpeechSynthesis → IndicF5 (MIT) fallback | — |
| Embeddings | Local ONNX: `multilingual-e5-small` (v1) → `BAAI/bge-m3` (v2) | ADR-0003 |
| Reranker | `bge-reranker-v2-m3` (ONNX, top-20) — measure CPU latency first | ADR-0003 |
| Doc parsing | Docling (MIT), offline on the developer laptop | — |
| Object storage | Supabase Storage behind a `StorageProvider` interface | ADR-0008 |
| Python hosting | HF Spaces (16 GB RAM free) or Cloud Run `asia-south1` | — |
| Frontend hosting | Vercel Hobby | — |
| Scheduling | GitHub Actions cron + Supabase Cron | — |
| Notifications | Web Push (VAPID); Telegram + WhatsApp test number optional | — |
| Observability | Langfuse (OpenTelemetry-instrumented) | — |
| Testing | pytest + pytest-recording (VCR) + Ragas (nightly) + promptfoo (CI) | — |
| Repo | **Public** GitHub repo | — |

**Fallback LLM ladder:** Groq (primary) → Mistral free (training opt-out enabled) — behind the provider abstraction.

---

## 4. Non-negotiable architectural rules

These are safety and correctness properties, not preferences. Do not weaken them without an ADR and Shabbir's approval.

1. **The LLM never invents pesticide dosage or waiting periods.** These come *only* from the deterministic agrochemical lookup (`app/safety/`), sourced from a version-stamped CIB&RC label table. If there is no verified entry, the system abstains.
2. **The deterministic safety layer runs *after* the LLM**, so no LLM output and no prompt-injected text can bypass the banned-molecule denylist or the dose lookup.
3. **Evidence-typed responses.** Every advisory separates `structured_data` (farm record), `live_data` (weather/price API), `retrieved_evidence` (source + year + page), `model_inference`, `recommendation`, `confidence`, and `abstained_because`.
4. **No promised accuracy figures.** Disease-diagnosis (and any model) accuracy is a **measured evaluation output**, never a target or a claim. Report cross-domain/field numbers, never lab numbers as headline.
5. **Abstention is a first-class outcome.** Low retrieval confidence, OOD image, or classifier/VLM disagreement → abstain and escalate (KVK / Kisan Call Centre 1800-180-1551).
6. **Evaluation-first.** The eval set exists before serious retriever tuning. Record a baseline before optimising.
7. **Deterministic where deterministic is better** (dates, growth stage, ET₀ balance, price statistics, citation validation). LLM only for language understanding and multi-factor reasoning. See `docs/ai/agent-design.md` §"Deterministic vs LLM".
8. **Write tools require explicit user confirmation** (`log_activity`, `create_reminder`). The agent never silently mutates the farm record.
9. **Retrieved corpus text is untrusted.** Delimit it, never let it trigger tools, and keep the safety layer after generation. Prompt-injection cases live in the eval set.

---

## 5. Data & privacy rules

- **Farmer data is personal data.** Treat farm location, crop condition, and photos as confidential.
- **Vision provider = Groq** specifically because Groq's Services Agreement §4.2 prohibits training on Inputs/Outputs by default and treats Customer Data as confidential. **Do not route farmer photos through any provider whose free tier trains on inputs or allows human review** (this is why Gemini free tier was rejected — see ADR-0004).
- **Secrets:** never in source, Git, docs, or the frontend bundle. Only environment variables. Keep `.env.example` with placeholders only. AgriAI variables are namespaced `AGRIAI_*`.
- **Supabase isolation:** AgriAI uses its **own** Supabase project (`agriai-db`), database, pgvector, auth, storage, and keys. The separate **BillingMars** project must never be read, modified, migrated, or shared. See ADR-0009.

---

## 6. Language scope

**MVP: Hindi + English only.** No third language now. Additional languages are a future item, added only when real human QA for that language is available. Retrieval does **not** translate every query to English first — it retrieves multilingually (see `docs/rag/rag-design.md`).

---

## 7. Repository map

```
apps/api/    Python FastAPI — the AI backend (routers have no business logic)
apps/web/    Next.js PWA — UI only, no AI logic
ingest/      Runs on the developer laptop, NOT in production (Docling needs ~6GB RAM)
evals/       Gold questions (JSONL) + Ragas + promptfoo
data/        Version-stamped agrochemical label table + banned-molecule denylists
supabase/    Supabase CLI project — config.toml + migrations/ (checked in; applied via `supabase db reset` locally, `supabase db push` to agriai-db)
docs/        Architecture, ADRs, roadmap, learning log — the source of truth alongside Git
```
Full structure and the "what does / does not belong here" rules: `docs/architecture/system-architecture.md`.

---

## 8. Workflow rules

- **Solo project.** Claude provides implementation plans and **exact Git commit messages**; **Shabbir runs all Git commands himself** from VS Code/terminal. Claude does not run Git. Do not assume a team/PR-review workflow unless told collaborators have joined.
- **GitHub is the source of truth.** Work incrementally; preserve working checkpoints. `main` is always deployable. Each phase ends with a tag (e.g. `v0.4-rag-baseline`). Docs and code change in the same commit.
- **Scope control:** every phase must ship a working, testable, demoable increment. A phase is not COMPLETED until its increment runs and its tests pass. Advanced features never block the core MVP — if an advanced feature stalls, it stalls, the MVP moves on.
- **No silent architecture changes.** If implementation reveals a better approach, stop, explain (Current / Recommended / Why / Trade-off / Impact), get approval, then update code + docs + an ADR together.

---

## 9. Claim discipline

Never write absolute competitive claims such as "all existing systems are stateless" — not in code comments, docs, README, or demo material. Use defensible wording: *"the public-facing systems we reviewed do not document per-farm persistent state or source-attributed evidence; AgriAI's differentiation is those two things."* The claim must survive a judge producing a counter-example.

---

## 10. Current status

**Phase 1 — COMPLETED (data foundation).** Supabase project `agriai-db` (own org, `ap-south-1`) is live with the 5 core migrations (profiles/farms/crops/farm_crops/activities), RLS Option B enforced by real JWT claims, and explicit `GRANT`s for the `authenticated` role (the local dev stack grants these by default; the real project does not, since "Automatically expose new tables" was deliberately left off). FastAPI backend verifies Supabase JWTs via JWKS/ES256. RLS isolation is proven both by an automated pytest suite (local) and by manual end-to-end verification against the real project. See `docs/roadmap/roadmap.md` for the phase tracker. Phase 2 (provider layer + first agent) is next.

## 11. Known open items / things to verify before they harden

- **Supabase Auth "Confirm email" is OFF on `agriai-db`** (turned off during Phase 1 verification to avoid the free-tier email rate limit). Deliberately left off for now since no real farmers are onboarding yet -- decide the real approach (email confirm ON + templates, phone/OTP, or custom SMTP) explicitly in Phase 2+'s onboarding work, not by default.
- ~~Supabase "2 active projects" limit: per-org or per-account?~~ **RESOLVED 2026-08-29** — confirmed against the live Supabase account: the Free plan's 2-active-project cap is **per account, across all orgs** (a new org does not grant extra free slots). `agriai-db` + `billingmars-db` now use both free slots; a future third project needs pausing/upgrading/deleting one of them.
- Groq zero-data-retention setting is offered to "Eligible Customers" — may be paid/enterprise-gated; unconfirmed. Base no-training term is not tier-gated, so not a blocker.
- Provider free-tier numeric rate limits are console-only now (Groq/Google/Mistral). Cite a dated console screenshot in ADRs, never a public docs number.
- CIB&RC "Major Uses of Pesticides" — obtain a current edition from ppqs.gov.in (automated fetch 403s; a known mirror is dated 2012). Version-stamp whatever is used.
- Reranker CPU latency is unverified — measure on the actual free-tier CPU before depending on it.
- TNAU Agritech Portal TLS was broken on automated fetch — verify in a browser before ingesting.
