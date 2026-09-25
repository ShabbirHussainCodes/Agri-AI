# ADR-0013: Abstention from validated evidence, not a similarity floor; code authors provenance

- **Status:** Accepted
- **Date:** 2026-09-25
- **Deciders:** Shabbir (+ Claude as advisor)
- **Supersedes in part:** ADR-0006 (the "one Pydantic model = LLM schema + FastAPI response" clause only). `docs/rag/rag-design.md` §1 and §6 (the retrieval "confidence floor") are revised to match.

## Context
`rag-design.md` planned a confidence floor: if the best retrieved chunk's similarity is below a threshold calibrated on the eval set, abstain before calling the LLM. The same threshold was meant to decide when the metadata widening cascade (crop+state → crop → unfiltered) had found a good-enough tier.

The first retrieval baseline (`evals/results/retrieval-2026-09-25.md`, 55 questions, local 113-chunk corpus) measured the input that floor would use. multilingual-e5-small's top cosine similarities are compressed into a narrow band, whether or not the corpus actually contains the answer:

| group | n | min | median | max |
|---|---:|---:|---:|---:|
| answerable | 31 | 0.755 | 0.846 | 0.906 |
| out_of_corpus | 8 | 0.764 | 0.825 | 0.856 |

Sweeping the threshold: 0.80 keeps 28/31 answerable questions but rejects only 1/8 out-of-corpus ones; 0.83 rejects 5/8 but already loses 8 answerable ones; only 0.86 rejects all 8, and by then 19 of 31 answerable questions are lost. No threshold separates the groups. Similarity measures "how alike", not "does this contain the answer".

Separately, under ADR-0006 the model wrote the whole `AdvisoryResponse`, including `retrieved_evidence` source names, years and pages, and `structured_data`. Code could only check these after the fact.

## Options considered
- **A. Keep the similarity floor, pick the "least bad" threshold.** Simple, no extra LLM call. But the data shows any threshold either discards a large share of good answers or lets most out-of-corpus questions through. That would be tuning a number we have measured does not work.
- **B. Use a cross-encoder reranker score (bge-reranker-v2-m3) as the relevance signal.** Rerankers score query–passage *relevance* and are usually better calibrated. But reranker CPU latency on the free tier is still unmeasured (CLAUDE.md §11), and the reranker is planned for Phase 10. Blocking Phase 4 on it would stall the MVP.
- **C. Decide abstention from evidence, after generation (chosen).** The model must back every claim from the corpus with `{passage number, verbatim quote}`. Code checks each citation. Abstention follows from what could be verified, not from a similarity score.

## Decision
1. **No similarity gate in retrieval.** `run_agent` retrieves for every question with the gate disabled (`NO_SIMILARITY_GATE`). The widening cascade stays in `app/retrieval/hybrid.py`, tested, but v1 retrieves unfiltered until there is a relevance signal that can judge a tier.
2. **Two schemas.** Turn B writes a small `DraftAdvisory` (`evidence_basis`, `citations[{passage, quote}]`, `model_inference`, `recommendation`, `confidence`, `abstained`, `abstained_because`). `app/agent/finalize.py` builds the `AdvisoryResponse` in code: the farm record, the weather result and **all** source metadata (title, publisher, year, page, licence, URL, chunk id) are copied from data the model never authors. The response shape the frontend sees is unchanged except that `EvidenceItem` gains `chunk_id`, `doc_type`, `licence`, `url`.
3. **Code decides abstention**, in this order, each step only more cautious:
   - the model abstained → abstain (its own reason kept);
   - `evidence_basis == "none"` → `insufficient_evidence`;
   - any citation fails validation (passage never shown, fewer than 4 words, or quote not found in that passage after whitespace/case/Unicode normalisation) → `invalid_citation`;
   - basis is `retrieved_passages` but there is no valid citation → `no_valid_citation`.
   When code overrides an answering model, the model's recommendation is replaced, never shown.
4. **Interim dose guard runs last** (`app/safety/interim_dose_guard.py`) over recommendation, reasoning and quotes. It is a Phase 4 stop-gap, not the Phase 6 safety layer.

## Why
It is what our own measurement supports. Verbatim-quote checking is deterministic and catches the most dangerous failure, an invented quote or source, without any threshold to tune. Removing provenance from the model's output removes a class of fabrication instead of detecting it afterwards.

## Consequences
- **Positive:** provenance cannot be fabricated; abstention is explainable per answer (`abstained_because`); no uncalibratable magic number; the model's schema is smaller (fewer tokens, less freedom).
- **Trade-offs:**
  - Out-of-corpus questions now cost one Turn B LLM call before abstaining (more tokens against Groq free-tier limits).
  - A **real but irrelevant** quote passes validation. That is a meaning question; Ragas Faithfulness in the Phase 4 eval measures it.
  - `evidence_basis` is self-reported. A model that answers from general knowledge and labels it `farm_and_weather_data` avoids the citation requirement. The `unanswerable` eval bucket measures how often that happens.
  - A model that "fixes" a typo in a damaged chunk (Docling reading-order damage, CLAUDE.md §11) fails validation and abstains. This fails safe, but it costs answers from damaged chunks.
- **Follow-ups:** measure all of the above in the full Phase 4 eval; revisit a relevance gate (and re-enable the cascade) when the reranker is measured in Phase 10.

## Links
ADR-0005, ADR-0006, ADR-0007, `docs/rag/rag-design.md` §1 and §6, `evals/results/retrieval-2026-09-25.md`, `apps/api/app/agent/finalize.py`, `apps/api/app/retrieval/citations.py`.
