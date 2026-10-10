# Testing Strategy

> Four layers. Conflating them is the common mistake. AI systems are non-deterministic — assert on facts, schemas, and tool-call sequences, never exact strings.

## Layer 1 — Deterministic unit tests (pytest)
Tool functions, validators, retrievers with mocked embeddings, prompt-template rendering, DB queries, the safety layer, date/stage math, ET₀ balance, price statistics. ~70% of the test count. Runs on every push.

## Layer 2 — Record/replay for API calls (pytest-recording / VCR)
Record real LLM/weather/price HTTP interactions once into committed cassettes; CI replays them at zero cost and zero flakiness. Scrub auth headers before committing. **Caveat:** cassettes freeze model behaviour — they test our code around the model, not the model. Re-record periodically.

## Layer 3 — Evals (LLM-as-judge + golden set)
Ragas over the 80–120 gold questions (Context Precision/Recall, Faithfulness, Response Relevancy). Run **nightly** or on PRs that touch prompts/retrieval, not on every commit. promptfoo for prompt A/B and regression, with its GitHub Action commenting results on PRs.

## Layer 4 — Contract testing
Force structured output and assert the **schema**, not the prose — the highest-value deterministic assertion we can get from a non-deterministic system. Every agent tool boundary and the `AdvisoryResponse` are contract-tested.

## Safety-specific tests (mandatory)
- Adversarial: the LLM **cannot** produce a pesticide dose that didn't come from the table.
- Prompt-injection cases from the eval set actually get neutralised.
- Abstention fires on OOD images and on below-floor retrieval.
- Banned-molecule denylist blocks a known-banned molecule even if a document recommends it.

## Vision (Phase 7)
- **No model file needed:** sanitising (EXIF, bombs, file types), the quality gate, the classifier wrapper against a fake backend (plus preprocessing parity against the model's own image processor), every branch of the decision (`app/vision/decision.py`), the vision-model parsing and its one retry, and the whole pipeline with fake models (`tests/test_vision_*.py`): a refused photo never reaches the vision provider, no dose comes from a model, the vision model's free text is guarded.
- **Real database and real local Storage API:** `tests/test_scans_api.py`, `tests/test_storage_supabase.py` (row-level security for a second farmer on rows and on photos, the caps, deletion).
- **Mutation checks** on the vision code (apply one small change, expect a failing test; 42 of 42 were caught when written).
- **Evaluation** is not a test: `evals/vision/` measures accuracy on field photos under a protocol written first. Its pure parts (metrics, calibration, head training, the report) have unit tests on synthetic data (`pytest evals/tests`, run from `apps/api`).

## Determinism note
`temperature=0` reduces but doesn't remove variance; `seed` is best-effort. Design assertions to tolerate this.

## What "COMPLETED" means
A phase is COMPLETED only when its demoable increment runs and the tests for that phase pass. See `docs/roadmap/roadmap.md`.
