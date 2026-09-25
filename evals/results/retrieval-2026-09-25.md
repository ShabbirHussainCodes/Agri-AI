# Retrieval baseline — 2026-09-25 14:26 UTC

Retrieval-only (no LLM). Cells are **recall@5 / recall@20 / MRR** for the gold page.
Produced by `evals/run_retrieval_eval.py`; full per-question detail is in `evals/_runs/`.

| scope | n | dense | lexical | hybrid (RRF k=50) |
|---|---:|---|---|---|
| **all with gold** | 38 | 0.53 / 0.76 / 0.47 | 0.58 / 0.68 / 0.38 | 0.61 / 0.82 / 0.49 |
| dose_safety_abstention | 7 | 0.14 / 0.57 / 0.12 | 0.14 / 0.29 / 0.08 | 0.14 / 0.57 / 0.13 |
| english_factual | 12 | 0.58 / 0.83 / 0.58 | 1.00 / 1.00 / 0.70 | 0.75 / 0.92 / 0.59 |
| hindi_factual | 6 | 0.83 / 1.00 / 0.77 | 0.00 / 0.00 / 0.00 | 0.83 / 1.00 / 0.77 |
| hinglish_code_mixed | 4 | 0.50 / 0.75 / 0.53 | 0.75 / 1.00 / 0.39 | 0.75 / 0.75 / 0.41 |
| multi_hop | 3 | 0.33 / 0.67 / 0.12 | 1.00 / 1.00 / 0.57 | 0.67 / 0.67 / 0.43 |
| prompt_injection | 2 | 0.00 / 0.00 / 0.03 | 0.00 / 0.50 / 0.05 | 0.00 / 0.50 / 0.04 |
| table_lookup | 4 | 1.00 / 1.00 / 0.71 | 0.75 / 1.00 / 0.51 | 0.75 / 1.00 / 0.77 |

## Top dense similarity by expected behaviour (input to the abstention floor)

| group | n | min | median | max |
|---|---:|---:|---:|---:|
| abstain:injection_attempt | 6 | 0.810 | 0.822 | 0.861 |
| abstain:no_verified_dose_source | 10 | 0.786 | 0.845 | 0.858 |
| abstain:out_of_corpus | 8 | 0.764 | 0.825 | 0.856 |
| answer | 31 | 0.755 | 0.846 | 0.906 |
