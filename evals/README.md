# evals/

Evaluation-first (ADR-0007). Build ~30 questions **before** the retriever; grow to 80–120.

- `questions.jsonl` — gold questions, each with `question`, `gold_source` (doc + page), `reference_answer`, `bucket`, `language`. Version-controlled.
- `ragas_run.py` — Ragas metrics (Context Precision/Recall, Faithfulness, Response Relevancy). Records baselines and deltas.
- `promptfoo.yaml` — prompt regression in CI.

Buckets: English factual (20) · Hindi factual (20) · table-lookup (15) · multi-hop (15) · **unanswerable/abstention (15)** · prompt-injection (10) · code-mixed Hinglish (10).

See `docs/testing/testing-strategy.md` and `docs/rag/rag-design.md` §9.
