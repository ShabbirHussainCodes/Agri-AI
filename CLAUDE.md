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
| Python hosting | Cloud Run `asia-south1` (HF Docker Spaces are no longer free, 2026-10-05) | ADR-0017 |
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

**Web app v0 — DEPLOYED AND SMOKE-TESTED (ADR-0017, 2026-10-05): web on Vercel Hobby, API on Cloud Run `asia-south1`, data on `agriai-db` (migrations applied, the measured 113-chunk corpus copied with `ingest/copy_corpus.py`, read-back identical).** First live run: signup, farm, a Hindi question answered in Hindi from the farm record. **Not yet checked live:** a corpus-backed answer with sources, irrigation/label cards (data unverified), the keep-alive workflow, a real phone, PWA install, Cloud Run cost against the free-trial credit.

Earlier build notes:** `apps/web` is a client-side Next.js PWA over the FastAPI backend: login, onboarding, farm diary, evidence-typed answers, irrigation log, Hindi default. The API gained CORS, `GET /farms/{id}`, saved advisories (migration `20261005120000`) and `/ask` caps (10/user, 35 global per day, 429 before any LLM call). Verified: lint, typecheck, build, 12 stubbed-API Playwright tests. **Unverified:** GitHub workflows, real phone, PWA install. Deploy steps and what was observed: `docs/deployment/deployment.md`.

**Phase 6 — IN PROGRESS (chemical safety layer, ADR-0016; built 2026-10-04, no tag yet).** A pesticide dose or waiting period now reaches a farmer **only** as a structured `agrochemical_label` card that code copies from a verified table row; the model never sees those numbers (`lookup_agrochemical` returns it none) and anything dose-shaped it writes is blocked after generation. The dose guard (`app/safety/interim_dose_guard.py`, now the permanent backstop) was measured at 12 of 47 adversarial phrasings with the Phase 4 patterns and blocks 47 of 47 after widening plus a grounded-number rule (`evals/chemical_guard_eval.py`, no quota). A banned-molecule guard (`app/safety/chemical_guard.py`) blocks every listed molecule; `status` only decides whether the message may name a legal status. **Both data files ship without verified content** (`data/denylists/`: 7 unverified seeds from recollection; `data/agrochemical/`: no rows), so no label card can appear until a human fills them from the CIB&RC documents (READMEs there). The `dose_safety_abstention` bucket and the interim-guard caveats below still describe the Phase 4 state.

**Regression check against the Phase 4 drafts (2026-10-05, `evals/replay_finalize.py`, no quota).** The hardened guard had cut behaviour accuracy from 53/55 to 51/55. Two causes:

- **en-fact-007 (false positive, fixed).** "tank" and "pump" in the application vocabulary made a water-harvesting tank a dose sentence. The four words were removed from layer 2 only; the leftover hole is recorded as gap-004.
- **tab-004 (correct by design).** Its answer is a trial's spray schedule. It was re-labelled `abstain` in `evals/questions.jsonl`, so the answer-expected set for Ragas is now 30, not 31.

After the fix: replay 53/55, adversarial dose cases 0 leaks / 47, false positives 0 / 17. The replay scores recorded drafts; a live run with the current guards is still open.

**Phase 5 — IN PROGRESS (irrigation water balance, ADR-0015; built 2026-10-04, no tag yet).** `get_irrigation_status` computes an FAO-56 root-zone water balance **in code** (`app/agronomy/`); the model only explains. The response gains `water_balance` (computed evidence, separate from `live_data`), and `app/safety/irrigation_guard.py` makes the model's verdict equal code's and every number it states appear in the evidence, otherwise the farmer gets code's own bilingual message. Output is in mm only. **The crop/soil reference table is fail-closed and currently entirely unverified**, so every irrigation question answers `cannot_assess` until a human verifies the rows against FAO-56 (`data/crop_water/README.md`). Verified locally 2026-10-04: migration applied and the full suite passed (334 passed, DB-backed tests included). Open-Meteo proven live the same day (99 daily rows). Still unverified: the live eval. See `docs/roadmap/roadmap.md` "Current position" for the exact list left before the tag.

**Phase 4 — COMPLETED (RAG v1, tag `v0.4-rag-baseline`).** `POST /farms/{id}/ask` now retrieves before it answers. Hybrid retrieval (dense `multilingual-e5-small` cosine + lexical `tsvector`, fused with RRF k=50 in Python) runs over the 113-chunk corpus. A two-turn agent follows: Turn A calls tools, Turn B writes strict `DraftAdvisory` JSON. `app/agent/finalize.py` then builds the `AdvisoryResponse` in code. Every citation must quote its passage verbatim, provenance is code-authored, and abstention is decided from validated evidence (ADR-0013 — the similarity floor was measured and dropped). An interim dose guard (`app/safety/interim_dose_guard.py`) scrubs dose and waiting-period statements from anything that reaches the farmer until Phase 6 exists.

Recorded baselines. Later phases must beat these, and Phase 10 reports its delta against them:

- **Retrieval** (`evals/results/retrieval-2026-09-25.md`, 38 questions with a gold page): hybrid recall@5 0.61, recall@20 0.82, MRR 0.49.
- **Agent end-to-end** (`evals/results/agent-2026-09-27.md`, all 55 questions, deterministic scoring):
  - behaviour accuracy 95%
  - dose statements reaching the farmer: 0
  - injection payload in the output: 0/8
  - citations validated on 100% of answers
  - gold page cited on 66% of answers
- **Ragas** (`evals/results/ragas-2026-09-29.md`, 31 answer-expected questions, judge `gpt-oss-20b`): context precision 0.69, context recall 0.87, faithfulness 0.94, answer relevancy 0.92, with 3 judge errors across all metrics. A smaller model judged these scores, so they are for comparing runs, not an absolute quality measure.

Read those numbers together. Citations validate on 100% of answers, yet faithfulness drops below 1 on multi-hop and Hinglish answers. A verbatim quote proves the passage exists, not that it supports the claim built on it. The same gap sits behind unans-001 (§11).

Two things from Phase 3 still constrain everything:

- **ADR-0012.** The Mandla crop calendar was extracted correctly and verified cell by cell against the PDF, then excluded anyway because the source's own values were unsafe for farmer-facing advice. Licence and provenance qualify a *source* for use, not its *content* for advice — safety-relevant agricultural claims need a domain sanity check too. Source content in the corpus is **not** AgriAI-verified knowledge, and the two must never be conflated in a response, in docs, or in demo material.
- **The corpus carries real application rates** (`B. subtilis @ 4 g/L`, `Tilt® 25% EC @ 1 mL/L`, and others in 10 chunks) as a research trial's protocol, not label recommendations. Rule 1 permits dosages only from the deterministic agrochemical lookup, and that lookup is Phase 6. Until then the only guards are the interim dose guard (a regex scrub, not a lookup) and the `dose_safety_abstention` eval bucket. In the Phase 4 run the model abstained on 10/10 of that bucket, and the guard caught the one dose the model echoed back from a farmer's question. **Nothing from this corpus goes in front of a real farmer until the Phase 6 safety layer replaces the interim guard.**

See `docs/roadmap/roadmap.md` for the phase tracker. Phases 5 and 6 are built and each waits on human data and checks (above); the roadmap lists exactly what is left before each tag.

## 11. Known open items / things to verify before they harden

- **Supabase Auth "Confirm email" is OFF on `agriai-db`** (turned off during Phase 1 verification to avoid the free-tier email rate limit). Deliberately left off for now since no real farmers are onboarding yet -- decide the real approach (email confirm ON + templates, phone/OTP, or custom SMTP) explicitly in Phase 2+'s onboarding work, not by default.
- ~~Supabase "2 active projects" limit: per-org or per-account?~~ **RESOLVED 2026-08-29** — confirmed against the live Supabase account: the Free plan's 2-active-project cap is **per account, across all orgs** (a new org does not grant extra free slots). `agriai-db` + `billingmars-db` now use both free slots; a future third project needs pausing/upgrading/deleting one of them.
- Groq zero-data-retention setting is offered to "Eligible Customers" — may be paid/enterprise-gated; unconfirmed. Base no-training term is not tier-gated, so not a blocker.
- Provider free-tier numeric rate limits are console-only now (Groq/Google/Mistral). Cite a dated console screenshot in ADRs, never a public docs number.
- CIB&RC "Major Uses of Pesticides" — obtain a current edition from ppqs.gov.in (automated fetch 403s; a known mirror is dated 2012). Version-stamp whatever is used.
- Reranker CPU latency is unverified — measure on the actual free-tier CPU before depending on it.
- TNAU Agritech Portal TLS was broken on automated fetch — verify in a browser before ingesting.
- Docling's reading order on two-column PDFs drops end-of-line characters and, near large tables, splices prose into table rows. Measured across both backends; pypdfium is better but not clean. Visibly damaged chunks are screened out, but pypdfium also reported out-of-page bbox geometry on pages 9–12 of `10568/180732`, so the damage zone may be wider than what the screen catches. 14 chunks from those pages are in the corpus with no visible damage — status unknown, to be measured by the eval set.
- The corpus is English-only. Hindi retrieval is untested against a Hindi *source*; the Hindi eval questions test Hindi query → English passage (ADR-0007), which is a different claim.
- Domain sanity validation (ADR-0012) is currently one person reading, not a test. Adding agronomic sanity assertions to the eval set is the follow-up.
- ~~**unans-001 (dangerous, fix first)**~~ **FIXED 2026-09-30 (ADR-0014):** real but irrelevant quotes passed citation validation ("sow wheat June–Sept" from Mandla rainfall prose). A question naming a crop is now answered only from documents curated as a source for that crop (`documents.crops_covered`), checked in code before Turn B and again in `finalize`. Still open: a real quote supporting an unsupported claim for a *covered* crop, and uncited general-knowledge answers labelled `farm_and_weather_data`.
- ~~**inj-003 bug**~~ **FIXED 2026-09-30:** a model abstention left `recommendation` and `model_inference` blank in 23 of 25 abstentions, so the farmer saw an empty answer. `finalize` now fills a blank abstention with the code-authored message for its reason (dose / injection / general), bilingual Hindi + English; an answer with no text is withheld (`empty_answer`); `AdvisoryResponse` rejects blank text as a backstop. Still open: inj-003's own over-refusal (it abstained on an answerable question).
- **en-fact-001:** a study finding was framed as a farm recommendation. No current metric catches this.
- **Retrieval ranking:** equal-weight RRF buries a single leg's #1 hit (en-fact-008). Ragas context precision (0.69) and Hinglish precision (0.25–0.45) point the same way. Context recall is 0 on en-fact-005, tab-004, inj-001 and inj-003. The fix belongs in retrieval tuning, measured as a delta.
- **Groq free tier is the binding constraint:** each model allows 30 RPM / 1K RPD / 8K TPM / 200K TPD, per the console on 2026-09-27. One `/ask` costs ~4.6k tokens at 6 passages (measured, Groq-reported, 15-question subset, 2026-09-30), so the generator model allows roughly 43 questions a day. A full Ragas run needs about two days of `gpt-oss-20b` quota. The `gpt-oss-20b` judge also fails with `json_validate_failed` on large multi-passage prompts; those failures are recorded as judge errors. Cutting the context budget from 6 to 4 passages was measured and rejected (`evals/results/token-budget-2026-09-30.md`). It saves 14.6% of tokens but loses multi-002, whose evidence sits at retrieval rank 5. Better ranking (Phase 10), not a smaller budget, is the lever. **LLM fallback is staged (decided 2026-09-30, `docs/roadmap/roadmap.md`):** token-budget cut first (measured, not adopted) → evaluate `gpt-oss-20b` as the generator (**failed the gate 2026-09-30**: 14/15 vs 15/15 on the paired subset, a dose-endorsing draft caught by code, and 3 provider JSON failures; `evals/results/generator-20b-2026-09-30.md`) → so **no `120b → 20b` fallback** → an independent provider later, after its own data-use check and eval. There is no fallback code and no ADR. Any fallback triggers only on quota or operational failure and never bypasses RAG, citations, abstention or the safety checks.
- The Groq console lists `qwen/qwen3.8-27b`, while ADR-0004 names `qwen/qwen3.6-27b`. Verify the current vision model name before Phase 7.
- ~~**`/ask` has no retry for a provider `json_validate_failed`.**~~ **DONE 2026-10-06 (Shabbir: "go"; no live LLM run).** When the provider rejects the model's output (`json_validate_failed` on Turn B, `tool_use_failed` or non-JSON tool arguments on Turn A) or Turn B comes back empty or does not parse as a `DraftAdvisory`, `loop.py` retries **once** with the same prompt, then returns an abstention written by code: `abstained_because: answer_generation_failed`, bilingual message, and any water balance code had already computed. It is saved and counted against the daily cap like any answer (its tokens were spent). Quota (429), authentication, network and every other error are **not** retried and still give the "could not get an answer" error. A retried answer goes through finalize and every guard like any other. Measured before: 120b 0 first-attempt failures in 30 questions, 20b 3 in 15; the eval report now also lists questions where the provider rejected an output at least once. **Not verified:** the exact shape of Groq's error object for these codes (read defensively in `_rejected_code`; tested against constructed SDK errors, not a recorded one), and that `tool_use_failed` is the code Groq uses on Turn A (from Groq's error vocabulary, never seen here). The Hindi wording of the new message is unreviewed. A retry costs another ~4.6k tokens when it fires.
- **Phase 5: the crop/soil table is unverified (blocker for any irrigation answer).** About 33 numbers from FAO-56 (Kc, stage lengths, rooting depth, depletion fraction, soil water capacity) must be read from the primary tables and marked verified by a named person (`data/crop_water/README.md`). Do **not** fill them from search snippets: those mixed rows. Every filled row also needs the ADR-0012 sanity check: `python -m app.agronomy.sanity_report --et0 <mm/day>` prints what the numbers imply (season ETc, TAW, RAW) to set against a published figure.
- **Phase 5: Open-Meteo is proven live** (2026-10-04: `et0_fao_evapotranspiration`, `precipitation_sum`, `past_days=92`, 99 daily rows). A wrong name would show up as `weather_unavailable`. The free API is non-commercial only.
- **Phase 5: direction of the model's known errors.** Constant root depth, no depletion-fraction correction for hot days, and no runoff all make the alert come **later** than ideal; ignoring forecast rain makes it come **earlier**. Listed in ADR-0015. One active crop per farm is assessed.
- **Phase 5: number grounding covers irrigation answers only** (those that carry a `water_balance`). It checks digits, not number words, and flags a rounded paraphrase (fails safe). Extending it to every answer would change Phase 4 behaviour: measure first. The ADR-0014 residual risk (an uncited general-knowledge answer labelled `farm_and_weather_data`) is therefore still open outside irrigation.
- **Phase 5: Hindi irrigation messages have had no native-speaker review** (`app/agronomy/messages.py`), against §6.
- ~~**Phase 5: `farm_context.days_since_sowing` uses the server's date**~~ **FIXED 2026-10-06** (see the live-app observations below): it now uses the farm calendar from `app/core/clock.py`. The water balance still takes the farm's local date from Open-Meteo, which is derived from the coordinates; for an Indian farm the two agree.
- **Migrations to apply on the remote `agriai-db`** before it is used: `20260930120000` (ADR-0014) and `20261004120000` (soil texture). Locally: `supabase migration up`, never `db reset`.
- **Existing farms have no `soil_texture` and often no location.** They stay `cannot_assess` until set through `PATCH /farms/{id}`. There is no frontend yet.
- **Phase 6: the denylist and the label table are empty of verified content (blocker for any label card and for any "banned in India" wording).** Download the current CIB&RC documents in a browser (ppqs.gov.in refuses automated fetches), check their licence, and fill `data/denylists/banned-central-v1.json` and `data/agrochemical/major-uses-v1.json` row by row from the primary document, never from snippets or memory. The 7 denylist seeds are recollection.
- **Phase 6: the banned guard is a lexicon.** A brand name, a synonym or a Hindi spelling not in `aliases` is not detected (3 declared gaps in `evals/chemical_guard_eval.py`). State-level bans are not covered. "Major Uses" is a summary; the pack label is the legal source and every card says so.
- **Phase 6: possible regression of the Phase 4 baseline.** The grounded-number rule (any number in the model's prose in a chemical conversation must come from the question, farm record, weather, balance or a code message) can turn a harmless RAG answer about a trial's protocol into a dose-guard abstention. Not measured yet: run `evals/replay_finalize.py` on the captured Phase 4 drafts (no quota) and compare behaviour accuracy with the 53/55 baseline before trusting the Phase 4 numbers for the new code. A proxy (the 31 reference answers fed through the new guards as if they were drafts) blocked 0 of 31, which is encouraging but is not captured model drafts.
- **Phase 6: Hindi wording of the banned-molecule and label-card messages has had no native-speaker review** (`app/safety/chemical_guard.py`, `app/safety/agrochemical_lookup.py`), against §6.
- **Phase 6: the eval measures phrasings this project thought of.** An unthought-of dose phrasing is exactly what it cannot count; the grounded-number rule exists because of that.
- **Web v0: apply migration `20261005120000` locally (`supabase migration up`) and run the full backend suite** (`test_advisories_db.py` has never run against a database). Then `cd apps/web && npm install && npm run dev`.
- **Web v0: the deployment files have never been executed** (`apps/api/Dockerfile`, `deploy/hf-space/make_bundle.py`, `.github/workflows/keepalive.yml`, `web-ci.yml`). The first deploy is their first test. Hosted-Supabase details (IPv4 pooler string, whether the project's JWKS lists keys) are listed as "verify" in the runbook, not asserted.
- **Web v0: no service worker, so no offline use; PWA install unverified. Hindi UI text unreviewed.** `/ask` caps count only saved answers, so a call that fails part-way with an error spends tokens without counting (ADR-0017); since 2026-10-06 a rejected model output no longer ends that way: it becomes a saved, counted abstention.
- **The web app shows `cannot_assess` for irrigation and never a label card** until the Phase 5 and 6 data files are filled by a human; the UI is honest about it but the demo will look empty there.
- **Web v0 (found in the first local run, 2026-10-05): model-written text is not translated.** A question asked in English gets an English answer even when the app is switched to Hindi; only code-authored messages (irrigation, dose, injection, banned-molecule, label card) are bilingual. A model abstention keeps the model's own text (`finalize`, deliberately, inj-003 fix), so "Cannot provide pesticide dosage without a verified source." shows in English in the Hindi UI. Options, none done: send the UI language as a hint in `/ask` (the contract already reserves `language?`; needs a Hindi-quality check first, against section 6), or show the code-authored bilingual message for every dose abstention. Either changes Phase 4 behaviour: measure with the eval before adopting.
- **Hosting (found 2026-10-05): a free Hugging Face Space can no longer run the API.** HF's own docs (huggingface_hub "Manage your Space") say Gradio and Docker Spaces on free `cpu-basic` need a PRO subscription (without one, creation fails with HTTP 402); only Static Spaces are free. The `HF Spaces (16 GB RAM free)` entry in section 3 and in `docs/deployment/deployment.md` is therefore out of date. Decision (Shabbir, 2026-10-05): deploy the API on Google Cloud Run, `asia-south1`, which section 3 already lists as the alternative, using the same root-Dockerfile bundle (`deploy/hf-space/make_bundle.py`). Cloud Run's free-tier numbers and whether `asia-south1` is covered were NOT verified (the pricing page could not be read from the session): set a budget alert and `--max-instances 1`, and check the console.
- **Deployed web (2026-10-05): the "How the AI reasoned" text stays English** even for a Hindi question (the model writes `model_inference` in English); the advice itself followed the question language. Same family as the untranslated-model-text item above.
- **Deployed: remote migration history was repaired** (the 7 Phase 1 migrations had been applied by another route under different version numbers; history now matches the repo). Never run `supabase db reset` against `agriai-db`. The remote `agriai-db` DB password was rotated 2026-10-05 after it appeared in a chat message.
- **Deployed: the `keepalive` workflow needs the repository variable `AGRIAI_API_URL` (GitHub, Settings, Secrets and variables, Actions, Variables) and one manual run.** Until then Supabase can pause after a week idle.
- **Live-app observations, verified 2026-10-06, FIXED 2026-10-06 (code, no live LLM run).** (a) "Sown 35 days ago" for a 2026-08-30 sowing on 5 Oct was an off-by-one every day between 00:00 and 05:30 IST: the saved advisory's `created_at` was 20:24:51 UTC (01:54 IST), the backend used `date.today()` on a UTC server and the farm page divided a UTC-midnight timestamp. Now `app/core/clock.py` `farm_today()` (fixed offset, setting `AGRIAI_LOCAL_UTC_OFFSET_MINUTES`, default 330) feeds `farm_context`, the irrigation early-exit date and the tool-failure date, and the farm page counts calendar days (`lib/dates.ts` `daysSince`). Tests with mutants on both sides. (b) The advice card showed the English crop name from the database while the header showed Hindi: `lib/crops.tsx` looks the name up in the `/crops` list, so saved advisories are fixed too. (c) "When should wheat be sown?" was answered from the farm record alone with nothing saying no document backed any crop advice: `AdvisoryResponse.limitations` is now a code-authored bilingual note, set when a crop is named, the answer is not an abstention, no water balance or label card is present and no document evidence is shown (`finalize.no_document_note`). Its Hindi wording is unreviewed. **Live-verified 2026-10-06 after the Cloud Run redeploy (revision 00003) and the Vercel deploy of `be63848`:** header and answer card both read "Sown 38 days ago" for a 29 Aug sowing, the crop name followed the UI language, and the "Limit of this answer" card appeared on the wheat sowing question and in the saved diary entry. **Not measured:** how many Phase 4 answers would carry the note; run `python evals/replay_finalize.py evals/_runs/<stamp>-agent.jsonl` (it now lists them, no quota). The API needs a Cloud Run redeploy for (a) and (c); Vercel redeploys on push to `main`. Still open for (c): a question that names no crop is not covered, and the model can still say something general in the advice text itself.

