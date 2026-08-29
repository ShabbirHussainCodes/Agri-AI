# ADR-0005: Deterministic agrochemical safety layer

- **Status:** Accepted
- **Date:** 2026-08-27
- **Deciders:** Shabbir (+ Claude)

## Context
AgriAI may need to state a pesticide, its dose, and its waiting period. A hallucinated dose is real physical harm, and in India the Insecticides Act 1968 makes a pesticide's registered label define its lawful crop-pest-dose combinations — off-label advice is advising an unlawful application.

## Options considered
- **LLM generates dosage with a "be careful" system prompt** — no guarantee; unsafe.
- **Deterministic lookup from a version-stamped CIB&RC label table + banned-molecule denylist, LLM never emits a dose** — a guarantee.

## Decision
The LLM **never** invents dosage or waiting periods. These come only from the deterministic `agrochemicals` table (version-stamped, source-dated). A banned-molecule denylist (central + state) runs first. The safety layer runs **after** the LLM so no output and no prompt-injected text can bypass it. If there is no verified entry, the system abstains.

## Why
Safety and legality must be deterministic, not probabilistic. Running the gate last also defeats prompt injection via the corpus. This is the clearest engineering-maturity signal in the project and the strongest positioning contrast with input-selling apps.

## Consequences
- **Positive:** no unsafe dose can reach a farmer; auditable, dated sources; strong demo/portfolio story.
- **Trade-offs:** requires sourcing and maintaining a current CIB&RC table (ppqs.gov.in 403s to automated fetch; known mirror is dated 2012 — a current edition must be obtained and version-stamped); state-level bans differ from central.
- **Follow-up:** adversarial tests that prove the LLM cannot emit a table-absent dose.

## Links
`docs/security/security-model.md`, `docs/ai/agent-design.md`.
