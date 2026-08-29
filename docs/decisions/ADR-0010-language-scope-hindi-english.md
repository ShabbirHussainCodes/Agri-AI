# ADR-0010: MVP language scope — Hindi + English only

- **Status:** Accepted
- **Date:** 2026-08-27
- **Deciders:** Shabbir (+ Claude)

## Context
AgriAI serves Indian farmers where voice and Indic languages matter. A third language was considered (Telugu had the strongest retrieval evidence and a production precedent; Marathi had the strongest agricultural weight and, being Devanagari, the best QA-from-Hindi-reading path).

## Decision
MVP ships **Hindi + English only.** No third language now. Additional languages are a future item, added only when real human QA for that language is available.

## Why
Shipping a language that cannot be QA'd is worse than shipping two well — a wrong agronomic term can mean a wrong chemical, and in this domain that has consequences. Discipline over breadth. Real-world Indic ASR sits at 20–30% WER, which further raises the QA bar per language.

## Consequences
- **Positive:** every shipped language is verifiable; focus on getting Hindi/English genuinely right (retrieval, ASR transcript UX, agronomic terms).
- **Trade-off:** narrower reach at MVP.
- **Follow-up:** revisit when a trusted QA partner for a specific regional language is available; a new ADR will record the choice. The message catalogue and multilingual retrieval are already built so adding one is not a refactor.

## Links
`docs/rag/rag-design.md`, `docs/frontend/frontend-architecture.md`.
