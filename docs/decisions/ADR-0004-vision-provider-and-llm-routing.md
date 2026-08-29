# ADR-0004: Vision = Groq qwen; chat = gpt-oss; Gemini free tier rejected

- **Status:** Accepted
- **Date:** 2026-08-27
- **Deciders:** Shabbir (+ Claude)

## Context
AgriAI sends farmer crop photos to a vision model and runs a text LLM for reasoning, on free tiers. Farmer photos are personal/confidential data.

## Options considered
- **Groq `qwen/qwen3.6-27b`** for vision — free, fast; Preview status; no strict schema / no prompt caching on this model.
- **Gemini Flash free tier** for vision — capable, but Google's API terms state content is used to improve products and "Human reviewers may read… your API input," with the instruction "Do not submit… personal information to the Unpaid Services," and no free-tier opt-out.
- Chat model: `llama-3.3-70b-versatile` was the plan, but it and `llama-3.1-8b-instant` were deprecated to Enterprise tier on 2026-08-16.

## Decision
Vision: **Groq `qwen/qwen3.6-27b`**. Chat/reasoning: **Groq `openai/gpt-oss-120b`** (quality) + `gpt-oss-20b` (fast). Strict JSON (Turn B) on gpt-oss-120b. Fallback LLM: Mistral free with training opt-out enabled. **Gemini free tier is rejected for any farmer content.**

## Why
Groq's Services Agreement §4.2 prohibits training on Inputs/Outputs by default and treats Customer Data as confidential; its DPA processes only on documented instructions — verified acceptable for routing farmer photos. Gemini's free tier is disqualified by human review + no opt-out for personal data. Llama models are no longer free-tier; gpt-oss additionally gives prompt caching (cached tokens don't count toward rate limits).

## Consequences
- **Positive:** privacy-safe photo routing; single-vendor simplicity for text+vision+speech; prompt caching lever.
- **Trade-offs:** vision is Preview (keep a fallback); vision model supports neither strict schema nor prompt caching, forcing a three-stage diagnosis flow with a short image-call prompt; provider free-tier numbers are console-only (cite dated screenshots).
- **Follow-up:** confirm whether Groq's zero-data-retention setting ("Eligible Customers") is available to us — not a blocker, an extra protection.

## Links
`docs/ai/ai-architecture.md`, `docs/ai/multimodal-vision.md`, `docs/security/security-model.md`, `claude/groq-data-use-check.md` (project notes).
