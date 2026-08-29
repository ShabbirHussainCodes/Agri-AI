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

## Determinism note
`temperature=0` reduces but doesn't remove variance; `seed` is best-effort. Design assertions to tolerate this.

## What "COMPLETED" means
A phase is COMPLETED only when its demoable increment runs and the tests for that phase pass. See `docs/roadmap/roadmap.md`.
