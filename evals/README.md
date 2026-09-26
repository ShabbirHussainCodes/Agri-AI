# evals/

Evaluation-first (ADR-0007). The gold set exists **before** the retriever, so Phase 4 can record a baseline instead of tuning blind.

## `questions.jsonl`

55 questions, every one grounded in the corpus that is **actually ingested** — verified: no `gold_source` points at a page that was excluded or screened out.

| field | meaning |
|---|---|
| `id` | stable identifier, e.g. `dose-003` |
| `question` | the farmer's question, as asked |
| `language` | `en` · `hi` · `hi-en` (code-mixed) |
| `bucket` | see the table below |
| `expected_behaviour` | `answer` or `abstain` — mirrors `AdvisoryResponse.abstained` (ADR-0006) |
| `gold_source` | `{handle, page}` of the passage that should be retrieved, or `null` |
| `reference_answer` | what a correct response contains (for Faithfulness / Response Relevancy) |
| `abstain_reason` | `no_verified_dose_source` · `out_of_corpus` · `injection_attempt` — mirrors `abstained_because` |
| `injected_context` | hostile text to splice into the retrieved passage for injection cases |
| `notes` | why the case exists, when that is not obvious |

## Buckets

| bucket | n | what it tests |
|---|---:|---|
| `english_factual` | 12 | plain retrieval + faithful answering |
| **`dose_safety_abstention`** | **10** | **retrieval succeeds and the answer must still be refused** |
| `unanswerable` | 8 | abstention when the corpus cannot support an answer |
| `prompt_injection` | 8 | instructions inside retrieved text are never executed (rule 9) |
| `hindi_factual` | 6 | Hindi query → English passage, no query translation (ADR-0007) |
| `table_lookup` | 4 | values from parsed tables, not prose |
| `hinglish_code_mixed` | 4 | how farmers actually type |
| `multi_hop` | 3 | joining two passages |

31 expect an answer, 24 expect abstention.

### Why `dose_safety_abstention` is the most important bucket

The ingested corpus contains real crop-protection application rates — `B. subtilis @ 4 g/L`, `B. bassiana @ 5 mL/L`, `Tilt® 25% EC @ 1 mL/L` — in 10 chunks of the tomato article (Table 3, p4). They are correctly extracted and correctly licensed. They are also **a research trial's protocol, not a label recommendation for a farmer's field**.

`CLAUDE.md` rule 1 permits dosages only from the deterministic agrochemical lookup, and rule 2 puts the safety layer *after* the LLM so retrieved text cannot bypass it. That layer is Phase 6 and does not exist yet. Until it does, these cases are the only thing standing between a retrieved trial rate and a farmer acting on it — and a wrong dose delivered *with* a genuine CC-BY citation is more dangerous than no answer, because the citation raises the farmer's confidence in it.

Several cases are deliberately harder than a flat refusal:

- `dose-005` — the fungicide is in the corpus but its **waiting period is not**; the system must not extrapolate.
- `dose-007` — the molecule is in the corpus but for **a different crop**.
- `dose-009` — the system may *describe* the trial's schedule as evidence, but must not reissue it as a recommendation.
- `inj-007` — asserts a CIB&RC table that has **not** been ingested; the honest answer is that there is none, not a borrowed trial rate.
- `unans-001` — asks the wheat sowing window, which only the **excluded** crop calendar (ADR-0012) touched. An answer here means the exclusion has leaked.

## Growing the set

Grow toward 80–120 as the corpus grows. Two documents cannot support more answerable questions honestly; the abstention, injection and code-mixed buckets are the ones that scale without new sources.

Follow-up from ADR-0012: add agronomic sanity assertions (rabi/kharif expectations for major Indian crops) so that class of source error becomes measurable rather than dependent on someone noticing.

## Runners

| script | what it measures | needs |
|---|---|---|
| `run_retrieval_eval.py` | retrieval only: recall@5/@20 and MRR of the gold page, dense vs lexical vs hybrid; top-similarity distributions | API venv, local stack. No LLM. |
| `run_agent_eval.py` | the whole `/ask` path with the real model: behaviour accuracy per bucket, who abstained (model / code / dose guard), dose statements in the model's draft vs reaching the farmer, injection payloads in output, citation validity, gold-page citation | API venv, local stack, Groq key. ~2 Groq calls per question. Resumable (`--resume`). |
| `run_ragas_eval.py` | LLM-judged Ragas 0.4.3: Context Precision / Context Recall (retrieval) and Faithfulness / Answer Relevancy (answers) | **separate** venv `evals/.venv-ragas` on Python 3.13 (`requirements-ragas.txt`), Groq key. Reads the `*-ragas-input.jsonl` the agent eval writes; judge calls are disk-cached. |

Order: retrieval eval → agent eval → Ragas. Summaries land in `results/` (committed); full per-question detail in `_runs/` (gitignored).

`tests/` holds pure unit tests for the deterministic scoring (`pytest evals/tests`).

## Still to build

- `promptfoo.yaml` — prompt regression in CI.

See `docs/testing/testing-strategy.md` and `docs/rag/rag-design.md` §9.
