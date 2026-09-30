# AgriAI Roadmap & Phase Tracker

**Rule:** every phase must ship a *working, testable, demoable increment*. A phase is not `COMPLETED` until its increment runs and its tests pass. Advanced features never block the core MVP — if an advanced feature stalls, it stalls; the MVP moves on.

**Statuses:** `PLANNED` · `IN PROGRESS` · `BLOCKED` · `COMPLETED`

**Checkpoint discipline:** each phase ends with a Git tag and a docs update in the same set of commits. `main` is always deployable.

---

## Current position

**Phase 4 — COMPLETED.** RAG v1 is live behind `POST /farms/{id}/ask`. Hybrid retrieval (dense + lexical, RRF k=50) feeds a two-turn agent. Citations are validated in code against a verbatim quote, abstention is decided from that validated evidence (ADR-0013), and an interim dose guard runs last. Three baselines are recorded under `evals/results/`:

- **Retrieval:** hybrid recall@5 0.61, recall@20 0.82.
- **Agent (55 questions):** behaviour accuracy 95%; 0 doses reached the farmer; 0/8 injection payloads in the output.
- **Ragas (31 questions, `gpt-oss-20b` judge):** context precision 0.69, context recall 0.87, faithfulness 0.94, answer relevancy 0.92.

Before Phase 5, three follow-ups run against these numbers:

1. ~~The unans-001 relevance / crop-mismatch safeguard.~~ Done 2026-09-30 (ADR-0014).
2. ~~The fix for an empty recommendation when the model abstains.~~ Done 2026-09-30.
3. ~~The token-budget measurement (6 → 4 passages).~~ Done 2026-09-30: the 6-passage budget was kept (`evals/results/token-budget-2026-09-30.md`). 4 passages saves 14.6% of tokens but loses multi-002.

**LLM fallback — staged, decided 2026-09-30 (Shabbir + Claude).** The measured problem is Groq quota, not provider outages, so the fallback is built only as far as measurement proves it is needed:

1. ~~Token-budget measurement~~ — done, not adopted (see above). Measured cost: ~4.6k tokens per `/ask`, i.e. ~43 questions a day.
2. ~~Evaluate `gpt-oss-20b` as the *generator*~~ — **done 2026-09-30, FAILED the gate** (`evals/results/generator-20b-2026-09-30.md`).
   - Accuracy on the paired 15-question subset: 14/15 vs 120b's 15/15 (multi-003).
   - It drafted a dose endorsement on dose-004; citation validation withheld it.
   - 3 provider-side JSON failures needed retries.
   - Consequence: 20b is not eligible as a generator, so there will be no `120b → 20b` fallback. The gate was 5 percentage points below 120b with identical safety, agreed before the run.
3. Is the need proven, i.e. quota errors seen in real development or demo use after step 1?
   - **No** → no fallback yet.
   - **Yes** → same-provider fallback `gpt-oss-120b` → `gpt-oss-20b`, on quota errors only.
4. An independent second provider comes later (post-MVP, Phase 11 at the earliest), and only after its own data-use check.

Standing rules for any fallback:
- Switch only on a quota or temporary operational failure, never because an answer looks poor.
- Never bypass RAG, citations, abstention, `DraftAdvisory` or the safety checks.

An ADR is written when step 3 says yes. Until then no fallback code exists; the `LLMProvider` interface keeps the door open.

---

## Scope tiers

- **MVP (must exist):** farm onboarding · activity logging · farm timeline · hand-rolled agent with read tools · RAG v1 with citations · weather/irrigation advice · eval set + Ragas baseline · Web Push reminder · deployed and phone-reachable.
- **Advanced:** image diagnosis with OOD + abstention · deterministic agrochemical safety layer · contextual retrieval · reranker · voice input · mandi advisor · Langfuse tracing · CI regression.
- **Post-hackathon:** fine-tuned field classifier · regional ASR · own Hinglish WER benchmark · farmer feedback dataset · durable workflows · second knowledge pack.

---

## Phases

| # | Objective | Ships (demoable increment) | Verified by | Tag | Status |
|---|---|---|---|---|---|
| 0 | Architecture & docs | This repo: CLAUDE.md, ADRs, docs skeleton, roadmap | A stranger can read the repo and understand the plan | `v0.0-architecture` | COMPLETED |
| 1 | Data foundation | DB schema + migrations + auth + RLS + onboarding + activity logging | pytest on models; create a farm end-to-end | `v0.1-foundation` | COMPLETED |
| 2 | Provider layer + first agent | Provider interfaces, hand-rolled tool loop, 2 read tools, evidence-typed response | Cassette-backed tests; one real question answered | `v0.2-agent` | COMPLETED |
| 3 | Corpus + eval set | Licence register, Docling ingest, eval questions written first | Chunks in DB with full metadata; eval JSONL committed | `v0.3-corpus-evalset` | COMPLETED |
| 4 | RAG v1 | Hybrid retrieval, RRF, citation validation, evidence-based abstention (similarity floor measured and dropped, ADR-0013), interim dose guard | **Ragas baseline numbers recorded** | `v0.4-rag-baseline` | COMPLETED |
| 5 | Weather + irrigation | Open-Meteo tool, ET₀ balance in code, LLM explains | Deterministic tests on the water-balance math | `v0.5-weather` | PLANNED |
| 6 | Safety layer + agrochemical data | Label table, denylist, dose lookup tool, schema enforcement | Adversarial tests: LLM cannot invent a dose | `v0.6-safety` | PLANNED |
| 7 | Image diagnosis | Quality gate, ONNX classifier, VLM reasoning, OOD, abstention UI | **Cross-domain accuracy measured & recorded in repo** | `v0.7-vision` | PLANNED |
| 8 | Voice | MediaRecorder → Whisper → editable transcript → agent | Own WER measurement on ~30 real utterances | `v0.8-voice` | PLANNED |
| 9 | Mandi advisor (modular, secondary) | Price ingest cron, statistics, advisory tool + UI card | Backtest the timing signal on historical data | `v0.9-mandi` | PLANNED |
| 10 | RAG v2 quality | Contextual retrieval, bge-m3, reranker | **Ragas delta vs Phase 4 baseline** | `v0.10-rag-v2` | PLANNED |
| 11 | Observability, CI, hardening | Langfuse, Sentry, promptfoo in CI, rate limits, upload validation | Traces visible; CI green on PR | `v0.11-hardening` | PLANNED |
| 12 | Demo polish | Timeline UI, demo script, README, diagrams | Full 5-minute run without a crash, twice | `v1.0-demo` | PLANNED |

> Phases 9 and 10 are advanced. If either stalls, the MVP (phases 1–8 core paths) still ships.

---

## Dependency notes

- Phases 1, 2, 3 are the foundation — nearly everything depends on them.
- The **eval set (Phase 3) precedes serious RAG tuning (Phase 4 and 10)** by rule.
- The **safety layer (Phase 6)** sits between any advisory output and the farmer; image diagnosis (Phase 7) depends on it for dose/label facts.
- The **mandi advisor (Phase 9)** depends only on the farm data model — it can be dropped whole without breaking anything else.

---

## Demo storyline (target for Phase 12)

1. Onboard a farm in ~30 seconds by voice.
2. Ask a question → cited answer with evidence types shown.
3. Upload a diseased leaf → top-3 + label-verified dose with waiting period.
4. Upload an out-of-distribution image → **show the abstention**.
5. Show the mandi timing card.
6. Show the farm timeline where all of it was recorded.
7. Show the evaluation numbers.

---

## Change log

- `2026-08-27` — Phase 0 started. Direction approved; ADR-0001…0010 created. Vision provider corrected to Groq `qwen/qwen3.6-27b`; default chat model to `gpt-oss-120b/20b`; storage to Supabase Storage behind an interface; language scope narrowed to Hindi + English. Groq data-use check cleared farmer-image routing.
- `2026-08-30` — Phase 1 completed. Supabase CLI local stack; 5 core migrations (profiles/farms/crops/farm_crops/activities) with RLS Option B (real JWT claims, `auth.uid()`-enforced policies); FastAPI skeleton with JWKS/ES256 verification; automated RLS proof (pytest); real `agriai-db` project created in its own Supabase org (`ap-south-1`), migrations applied, RLS + write-isolation proven end-to-end against the live project. ADR-0011 (Python 3.14 dev runtime) added, superseding ADR-0001's version clause.
- `2026-09-03` — Phase 2 completed. Groq provider (tool calling + strict-schema structured output) behind `LLMProvider`; hand-rolled agent loop with `get_farm_context` called deterministically (not an LLM-optional tool -- a bug fix, see `app/agent/loop.py`'s module docstring for the Turn A/B prompt-leak it corrected) and `get_weather` as the one LLM-gated tool; `POST /farms/{id}/ask` returns an evidence-typed `AdvisoryResponse`. Cassette-backed test (`pytest-recording`) verifies the real Groq + Open-Meteo flow so CI never needs a live `GROQ_API_KEY`; `vcr_config` (`tests/conftest.py`) redacts auth headers and excludes local/internal hosts from the cassette entirely.
- `2026-09-08` — Phase 3 completed. Corpus licence register with two item-level-verified CC-BY-4.0 sources (CGSpace); Docling ingest pipeline with structure-aware chunking, so every chunk carries `page_no` and `section_path`; embeddings from a local ONNX `multilingual-e5-small`, built from heading-contextualised text while the stored content stays raw so citations quote the real passage; `documents`/`chunks` tables with an HNSW cosine index and a generated `tsvector`, read-only for `authenticated` following the `public.crops` precedent. The PDF backend was switched to pypdfium by measurement, not preference, and chunks damaged by extraction are screened out with their reason printed. **113 chunks ingested** (19 + 94); 35 excluded or screened out. ADR-0012 added: the Mandla crop calendar was extracted correctly and verified against the PDF, then excluded because the source's own values were not safe for farmer-facing advice — establishing that licence and provenance qualify a *source*, not its *content*, and that source content is not AgriAI-verified knowledge. Eval set is **55 questions, not the ~30 originally planned**: two documents cannot honestly support more answerable questions, so the set is weighted towards abstention, injection and code-mixed cases, with `dose_safety_abstention` (10) the most important bucket because the corpus carries real application rates while the Phase 6 safety layer does not yet exist.
- `2026-09-29` — Phase 4 completed. Hybrid retrieval: dense e5 cosine plus lexical `tsvector` with the query rewritten from AND to OR, fused by RRF k=50 in pure Python; the widening cascade is built but disabled. The agent retrieves before Turn B, and `app/agent/finalize.py` builds the response in code — every citation must quote its passage verbatim, provenance is code-authored, and abstention is decided from validated evidence. **ADR-0013** records that the planned similarity floor was measured and dropped: top similarities for answerable (0.755–0.906) and out-of-corpus (0.764–0.856) questions overlap. It supersedes ADR-0006's one-model clause. An interim regex dose guard runs last until Phase 6. Three baselines recorded:
  - **Retrieval (38 questions with a gold page):** hybrid recall@5 0.61, recall@20 0.82, MRR 0.49.
  - **Agent (55 questions, deterministic scoring):**
    - behaviour accuracy 95%
    - dose-safety bucket 10/10 abstained
    - 0 doses reached the farmer
    - injection payload in the output 0/8
    - citations validated on 100% of answers
    - gold page cited on 66% of answers
  - **Ragas (31 answer-expected questions):** context precision 0.69, context recall 0.87, faithfulness 0.94, answer relevancy 0.92, with 3 judge errors. The judge is `gpt-oss-20b`, a smaller model than the `gpt-oss-120b` generator, which also avoids self-grading.

  Groq free-tier quota (200K tokens/day per model) paced the evals: the agent eval resumed across days, and Ragas ran over two days from a judge-call cache. Known gaps are carried in CLAUDE.md §11. The dangerous one is unans-001: a real quote that is irrelevant to the question still passes citation validation.
