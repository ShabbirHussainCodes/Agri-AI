# ADR-0014: Crop-scoped evidence — a question naming a crop is answered only from documents curated as a source for it

- **Status:** Accepted
- **Date:** 2026-09-30
- **Deciders:** Shabbir (+ Claude as advisor)
- **Extends:** ADR-0013 (adds one abstention rule and a pre-generation passage filter). Applies the ADR-0012 principle — a human decides what a source is qualified *for* — to crops.

## Context
The Phase 4 agent eval (`evals/results/agent-2026-09-27.md`) had one dangerous miss, **unans-001**: "When should I sow wheat in Madhya Pradesh?" The corpus has no wheat sowing source, so the correct behaviour is to abstain. Instead the model cited two **real** sentences from the Mandla kitchen-garden manual:
- "nearly 90% of rainfall is concentrated between June and September"
- "Planting must therefore be adjusted to each season's rainfall pattern"

From these it answered "sow wheat at the onset of the monsoon (June–September)". Wheat is a rabi crop, so that is the wrong season. Both quotes passed ADR-0013 validation because they exist verbatim in the passage. The cited passage never mentions wheat.

ADR-0012's exclusion held: the excluded crop calendar was not retrieved. The model built the answer from rainfall prose.

Two things were measured before choosing (captured run `20260926T134710Z-agent.jsonl`):
- **A string check is gameable.** The same retrieval also returned the manual's Rationale chunk, which contains "rice and wheat (primary cereals provided by the PDS)" and "black cotton soils". A rule like "the cited passage must mention the crop" would have passed if the model had cited that chunk.
- **A quote-window variant was too strict.** Requiring the crop within ±300 characters of the quote wrongly withheld tab-002, a table chunk that names tomato only in its heading.

## Options considered
- **A. The cited chunk must mention the crop (string match).** Deterministic and cheap, but gameable by incidental mentions, as shown above.
- **B. Curated per-document crop coverage (chosen).** A human records which crops each document is a *source for*. Code checks that against the crops the question names.
- **C. A claim-support verifier (NLI model or LLM judge).** This is the only option that also catches "a real quote, but an unsupported claim" beyond crops. It was rejected for now:
  - An LLM version adds a Groq call to every `/ask`, on a budget of about 40 questions a day, and it is non-deterministic.
  - A local NLI model needs a cross-lingual benchmark first (Hindi recommendation vs English quote).
  - It is a Phase 10 candidate.
- **A pre-generation abstain gate** ("the question names an uncovered crop → abstain before the LLM") was also rejected. It would block "Kya aaj mujhe apne gehun ko paani dena chahiye?" (the `test_ask` cassette case), which is correctly answered from the farm record and the weather and needs no corpus source.

## Decision
1. **`public.documents.crops_covered text[] not null default '{}'`** (migration `20260930120000`). The values come from `ingest/sources.yaml`:
   - The field is required for every approved item, with its reason written next to it.
   - `run.py` writes it on ingest. `sync_crops_covered.py` updates it without re-ingesting.
   - An empty list means the document covers no crop (fail-closed).
2. **Crop detection** (`app/safety/crop_scope.py`) uses a token-based lexicon with English, Hindi and Hinglish forms. Tokens are matched instead of regex `\b`, because Devanagari vowel signs are not regex word characters.
   - Ambiguous words are left out: "gram" (also a weight unit), "आम" (also "generally"), "lime" (also soil lime).
   - "black cotton soil" does not count as cotton.
   - In a grafting question, the rootstock species is not treated as the crop being asked about.
   - No crop is inferred from the farm record.
3. **Passage scoping before Turn B** (`run_agent`): when the question names crops, Turn B sees only passages from documents that cover **all** of them. If none remain, the passage block says that no source covers the crop. This filters evidence; it does not abstain. A crop question can still be answered from farm and weather data.
4. **Post-check in `finalize_advisory`**, after `no_valid_citation` and before the dose guard: if any validated evidence comes from a document that does not cover every named crop, the reason is `crop_not_covered` and the model's answer is replaced, as for the other code overrides. This is defence in depth: step 3 makes it unreachable today, and it keeps `finalize` safe on its own.
5. **Coverage decisions, reviewed 2026-09-30:**
   - Tamil Nadu tomato trial → `[tomato]`. Eggplant is only the rootstock there; marking it covered would let a brinjal question be answered from tomato data.
   - Mandla kitchen-garden manual → the kitchen-garden vegetables, spices and fruit its prose discusses. It covers no field crops: wheat and rice appear only as PDS rations.

## Why
It closes the measured failure deterministically, with no model call and no threshold, and it cannot be gamed by incidental mentions, because coverage is a human decision rather than a string match. It also puts the "what is this source qualified for" judgement where ADR-0012 already put it: with a named reviewer, in Git.

## Consequences
- **Measured (offline replay, `evals/replay_finalize.py`, same 55 recorded drafts):**
  - behaviour accuracy rises from 52/55 to 53/55; unans-001 now abstains with `crop_not_covered`
  - no question changed from correct to incorrect
  - five questions would get a different passage block (dose-007, unans-001, unans-004, unans-006, unans-007); verify them with a live run
- **Fail-open for unknown crop words.** A crop missing from the lexicon is not detected, and that question is not crop-scoped. The lexicon lists field crops the corpus does *not* cover for this reason.
- **Residual risk (not solved here):**
  - An answer the model labels `farm_and_weather_data`, with no citation but using general knowledge, is only stopped by the Turn B prompt.
  - "A real quote, unsupported claim" beyond crops (e.g. rainfall → sowing date for a covered crop) remains. It is measured by Ragas faithfulness; option C is the long-term fix.
- **Maintenance:** every new document needs a `crops_covered` decision, or ingest refuses it. `tests/test_crop_scope.py` fails on an unknown key and asserts that no current document covers wheat.
- The remote `agriai-db` project needs this migration before any corpus is loaded there.

## Links
ADR-0012, ADR-0013, `app/safety/crop_scope.py`, `app/agent/finalize.py`, `ingest/sources.yaml`, `docs/rag/rag-design.md` §6.
