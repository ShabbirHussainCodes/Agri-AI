# Learning Log

> This project is also a way to learn modern AI + software engineering by building. Keep short, honest notes here as you go — not tutorials, but *what you learned by doing this, in your own words*. These become interview stories and a record of your growth.

## How to use this folder

One markdown file per phase (or per meaty concept). Keep each note to: **what it is → why AgriAI needs it → how it works here → what I learned / what surprised me.** English for technical terms; your own voice for the rest.

## Suggested notes (create as you reach them)

| File | Concept | Phase |
|---|---|---|
| `01-tool-calling.md` | How a hand-rolled tool loop actually works (messages, tool_calls, results, termination) | 2 |
| `02-structured-outputs.md` | Constrained decoding, Pydantic as a contract, the two-call split | 2 |
| `03-rag-evaluation.md` | Ragas metrics, retrieval-vs-generation debugging, golden datasets | 3–4 |
| `04-hybrid-search.md` | pgvector, tsvector, HNSW, GIN, RRF, the Hindi-stemmer problem | 4 |
| `05-deterministic-safety.md` | Why safety logic is code not prompt; running the gate after the LLM | 6 |
| `06-calibration-ood.md` | ECE, temperature scaling, open-set detection, why lab accuracy lies | 7 |
| `07-provider-abstraction.md` | Adapter pattern, graceful degradation, vendor risk | 2+ |
| `08-testing-ai.md` | VCR cassettes, LLM-as-judge, contract tests, tolerating non-determinism | 11 |
| `09-observability.md` | OpenTelemetry, tracing an agent, what to actually measure | 11 |

## The headline lesson to keep honest

An **honest measured field number with a working abstention path** is a stronger portfolio artifact than an impressive lab number. Same for RAG: **evaluated retrieval with recorded metrics** beats "I built RAG." Write these up when you have the numbers — they are the parts of this project that make you stand out.
