# ADR-0007: Multilingual retrieval without query translation; evaluation-first

- **Status:** Accepted
- **Date:** 2026-08-27
- **Deciders:** Shabbir (+ Claude)

## Context
Farmers ask in Hindi (and Hinglish) over a corpus that is partly English. There is a choice about where, if anywhere, to translate.

## Options considered
- **Translate query → English, then retrieve (tRAG)** — the obvious approach; published as the weakest (translation errors limit coverage, and they happen before retrieval where they're unrecoverable).
- **Retrieve multilingually with a multilingual embedder (MultiRAG), normalise language at generation (CrossRAG)** — published as stronger, with larger gains for low-resource languages.

## Decision
Do not translate every query to English before retrieval. Retrieve multilingually with a multilingual embedder, generate in the farmer's language, keep citations on the original source, and do not translate the corpus. Domain-grounded query rewriting (colloquial/Hinglish → agronomic terms) is a separate, worthwhile operation; generic query rewriting is not. Evaluation-first: the eval set exists before serious retriever tuning; record a baseline (Phase 4) before v2 optimisation (Phase 10).

## Why
The evidence favours retrieve-multilingually over translate-query, especially for lower-resource languages, and query translation discards information before the irreversible retrieval step. Evaluation-first prevents blind tuning and produces the project's strongest differentiating artifact (measured RAG).

## Consequences
- **Positive:** better multilingual retrieval; citations stay truthful; measurable progress.
- **Trade-offs:** relies on a strong multilingual embedder (e5-small → bge-m3); Hindi lexical search is weak (no PG stemmer) and leans on the dense side or bge-m3 sparse vectors.

## Links
`docs/rag/rag-design.md`, `docs/testing/testing-strategy.md`.
