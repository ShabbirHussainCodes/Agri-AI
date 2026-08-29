# AgriAI Roadmap & Phase Tracker

**Rule:** every phase must ship a *working, testable, demoable increment*. A phase is not `COMPLETED` until its increment runs and its tests pass. Advanced features never block the core MVP — if an advanced feature stalls, it stalls; the MVP moves on.

**Statuses:** `PLANNED` · `IN PROGRESS` · `BLOCKED` · `COMPLETED`

**Checkpoint discipline:** each phase ends with a Git tag and a docs update in the same set of commits. `main` is always deployable.

---

## Current position

**Phase 0 — IN PROGRESS.** Architecture and documentation being created. No application code yet. Implementation begins only when Shabbir explicitly moves the project into the implementation phase.

---

## Scope tiers

- **MVP (must exist):** farm onboarding · activity logging · farm timeline · hand-rolled agent with read tools · RAG v1 with citations · weather/irrigation advice · eval set + Ragas baseline · Web Push reminder · deployed and phone-reachable.
- **Advanced:** image diagnosis with OOD + abstention · deterministic agrochemical safety layer · contextual retrieval · reranker · voice input · mandi advisor · Langfuse tracing · CI regression.
- **Post-hackathon:** fine-tuned field classifier · regional ASR · own Hinglish WER benchmark · farmer feedback dataset · durable workflows · second knowledge pack.

---

## Phases

| # | Objective | Ships (demoable increment) | Verified by | Tag | Status |
|---|---|---|---|---|---|
| 0 | Architecture & docs | This repo: CLAUDE.md, ADRs, docs skeleton, roadmap | A stranger can read the repo and understand the plan | `v0.0-architecture` | IN PROGRESS |
| 1 | Data foundation | DB schema + migrations + auth + RLS + onboarding + activity logging | pytest on models; create a farm end-to-end | `v0.1-foundation` | PLANNED |
| 2 | Provider layer + first agent | Provider interfaces, hand-rolled tool loop, 2 read tools, evidence-typed response | Cassette-backed tests; one real question answered | `v0.2-agent` | PLANNED |
| 3 | Corpus + eval set | Licence register, Docling ingest, ~30 eval questions written first | Chunks in DB with full metadata; eval JSONL committed | `v0.3-corpus-evalset` | PLANNED |
| 4 | RAG v1 | Hybrid retrieval, RRF, citation validation, abstention floor | **Ragas baseline numbers recorded** | `v0.4-rag-baseline` | PLANNED |
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
