# RAG Design

> Rule: do not call it RAG unless retrieval actually influences generation. Evaluation-first (ADR-0007): the eval set exists before serious tuning.

## 1. Two builds

**v1 (build first — works and is demoable):**
```
Docling parse (laptop) → recursive chunking (~500 tokens, 15% overlap)
  → metadata attach → e5-small embed (local ONNX, "passage:" prefix)
  → Supabase Postgres: pgvector HNSW on vector(384) + tsvector GIN
  → metadata filter from farm profile (with widening cascade)
  → hybrid dense + full-text, fused with RRF (k=50)
  → top-20 → confidence floor (abstain if below) → generate with numbered citations
  → code-level citation validation
```

**v2 (quality):** + contextual retrieval at ingest · bge-m3 embedder (1024-d) · bge-reranker-v2-m3 on top-20 · domain-grounded query rewriting · selective routing. Record the Ragas delta vs the v1 baseline.

## 2. Multilingual retrieval (ADR-0007)

Do **not** translate every query to English before retrieval. Retrieve multilingually with a multilingual embedder (published evidence favours retrieve-multilingually over translate-query), generate in the farmer's language, keep citations pointing at the original source, and do not translate the corpus. Domain-grounded query rewriting (colloquial/Hinglish → crop names, scientific pest names, agronomic terms) is a *separate* operation from translation and is worth doing; generic "improve this query" rewriting is not (it can hurt retrieval).

## 3. Hindi lexical caveat

PostgreSQL ships no Hindi Snowball stemmer, so Hindi full-text uses `to_tsvector('simple', …)` (lowercasing + stopwords, no stemming). Two accepted mitigations: (a) let the dense side carry Hindi while lexical carries English agronomic terms, crop and chemical names — where BM25 is strongest anyway; or (b, preferred in v2) use bge-m3's learned sparse vectors instead of tsvector — language-agnostic, no stemmer needed. Verify on the instance with `\dF`.

## 4. Metadata (real FK columns, not JSONB)

Per chunk: `source_org`, `doc_type`, `crop_id`, `state`/agro-climatic zone, `language`, `published_year`, `page_no`, `section_path`.

- **`published_year` matters for safety:** pesticide recommendations get banned; an old advisory recommending a now-prohibited molecule is worse than no answer. Treat recency as a hard filter or scoring penalty.
- **Widening cascade to avoid over-filtering:** exact (crop+state) → drop state → drop crop → national/generic, and tell the model which tier it got so the answer can say "no state-specific guidance found; here is the national recommendation."

## 5. Chunking & context

Recursive/fixed chunking (semantic chunking rejected — cost not justified). v2 adds contextual retrieval: for each chunk, a cheap LLM writes a 50–100 token situating preamble ("this chunk is from the ICAR package of practices for Bt cotton in Maharashtra, sowing section") prepended before embedding and BM25 — a one-time offline cost, so the free-tier TPM limit doesn't bite. Fixes orphaned chunks (e.g. a dose table with no crop name in it).

## 6. Grounding, citations, abstention

- Numbered chunks `[1]…[n]`; every factual sentence carries a marker; code validates each cited index exists and drops/flags uncited factual sentences.
- Confidence floor (calibrated on the eval set) abstains before the LLM when retrieval is weak.
- Safety-critical facts (dose, chemical, banned status) abstain unless a verified citation/table entry exists.

## 7. Corpus & licensing (tiered)

- **A — ingest freely:** FAO Knowledge Repository, data.gov.in datasets (GODL-India), Apache-2.0 HF datasets (CGIAR/DigiGreen, KisanVaani).
- **B — one email away:** Vikaspedia (operational follow-up; must not block the architecture).
- **C — link & cite, don't bulk-ingest:** ICAR, PAU PoP, ICAR-IIHR, TNAU (store URL + title + our own short summaries; retrieve and cite).
- **D — don't touch:** CABI Compendium.

A machine-readable licence register lives at `ingest/sources.yaml` (url, licence, permission status). Verify TNAU TLS in a browser before ingesting; the KCC dataset is for intent taxonomy and eval-set construction, not authoritative ground truth.

## 8. Document parsing

Docling (MIT) on the developer laptop (TableFormer handles the merged/spanning cells agri dose tables are full of; ~6 GB RAM, so offline not in-container). For scanned Hindi, bake off Docling+Tesseract(`hin`), Docling+RapidOCR, Marker, and Mistral OCR on 5–10 representative pages before committing; a one-time paid OCR pass on the hardest scanned pages is acceptable (ingest cost, not a runtime dependency).

## 9. Evaluation (Ragas + Langfuse + promptfoo)

80–120 hand-written gold questions with source doc + page, JSONL in `evals/`. Buckets: 20 English factual, 20 Hindi factual, 15 table-lookup, 15 multi-hop, **15 unanswerable (abstention)**, 10 prompt-injection, 10 code-mixed Hinglish. Write ~30 before building the retriever. Metrics: Context Precision/Recall, Faithfulness, Response Relevancy — the split answers "is retrieval bad or is the prompt bad?"
