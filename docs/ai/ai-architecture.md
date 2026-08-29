# AI Architecture

> Governs how AgriAI uses models. Safety rules here are non-negotiable (see `CLAUDE.md` §4).

## 1. Providers and routing

Everything goes through a **provider abstraction** (`app/providers/`) so a rate limit or a deprecation never reaches business logic. Interfaces: `LLMProvider`, `VisionProvider`, `SpeechProvider`, `EmbeddingProvider`, `RerankProvider`.

| Job | Model | Notes |
|---|---|---|
| Chat / reasoning | Groq `openai/gpt-oss-120b` | fast path `gpt-oss-20b`; prompt caching only on gpt-oss family; cached tokens don't count toward rate limits |
| Strict JSON (Turn B) | Groq `openai/gpt-oss-120b` | strict schema supported on gpt-oss-20b/120b (and qwen3.8-27b) |
| Vision | Groq `qwen/qwen3.6-27b` | 5 images/req, 20 MB, **2,048 tokens/image**; Preview status — keep a fallback; no strict schema, no prompt caching on this model |
| Speech-to-text | Groq `whisper-large-v3-turbo` | free-tier file cap 25 MB; test Hindi ourselves (Groq docs say only "Multilingual") |
| TTS | Browser SpeechSynthesis → IndicF5 (MIT) | Groq TTS has no Hindi |
| Embeddings | local ONNX `multilingual-e5-small` (v1) → `bge-m3` (v2) | Groq has no embeddings endpoint |
| Rerank | local ONNX `bge-reranker-v2-m3` | measure CPU latency before depending on it |
| Fallback LLM | Mistral free (training opt-out ON) | |

**Rate-limit reality:** provider free-tier numbers are console-only now. Keep the fast path and prompt caching (stable system-prompt prefix on gpt-oss) as the main levers, and the fallback provider ready.

## 2. The two-call flow

Groq cannot combine strict structured output with tools or streaming. So:

- **Turn A (evidence):** streaming tool loop, no strict schema. Gathers farm context, weather, retrieved chunks, label lookups, image analysis.
- **Turn B (answer):** separate call, no tools, strict `json_schema`, emits the evidence-typed object.

This is also *where provenance and confidence attach*, and it enforces the epistemic separation by construction.

## 3. Evidence-typed response (the contract)

Every advisory is one object (one Pydantic model = LLM schema + FastAPI response + OpenAPI). Fields:

- `structured_data` — from the farm record (crop, stage, area, soil card values).
- `live_data` — from weather/price APIs, timestamped.
- `retrieved_evidence[]` — each with `source_org`, `doc_title`, `published_year`, `page`, and the quoted span.
- `model_inference` — what the model concluded.
- `recommendation` — the actionable output.
- `confidence` — calibrated where possible; never raw softmax presented as truth.
- `abstained` + `abstained_because` — a first-class outcome.
- `citations_valid` — set by the code-level citation check, not the model.

The UI renders these distinctly: "what a document says" must look different from "what the model thinks".

## 4. Deterministic vs LLM

Deterministic code owns anything with a safety, legal, or arithmetic character: pesticide dose & waiting period, banned-molecule checks, days-after-sowing / growth stage, ET₀−rainfall irrigation balance, price statistics, retrieval confidence floor, citation validation. The LLM owns intent understanding, domain-grounded query rewriting, explanation, and multi-factor reasoning. Full table: `docs/ai/agent-design.md`.

## 5. Grounding & abstention

- Numbered-chunk citations; every factual sentence must carry a marker; code strips markers and verifies each cited index exists.
- A calibrated **retrieval-score floor** abstains *before* the LLM call when evidence is weak.
- For anything with a safety consequence (dose, chemical, banned status): **abstain unless a verified citation/table entry exists.** Never interpolate.

## 6. Prompt architecture (summary)

- A stable system-prompt prefix (for gpt-oss prompt caching) that states role, safety rules, and output contract.
- Retrieved corpus text goes in a clearly delimited **untrusted** block; it may not trigger tools.
- Image-call system prompts are kept short (no prompt caching on the vision model; each image already costs 2,048 tokens).
- Prompts are versioned files under `app/agent/prompts/` and are covered by promptfoo regression.

## 7. What we deliberately do not do

No fully agentic self-correcting RAG loops (measured to underperform hybrid+rerank at higher cost); no multi-agent crew; agency is limited to routing, genuine multi-hop, and a single corrective retry. See ADR-0002 and `docs/rag/rag-design.md`.
