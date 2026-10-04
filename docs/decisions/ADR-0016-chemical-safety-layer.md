# ADR-0016: Chemical safety layer: a banned-molecule guard, a hardened dose guard, and doses only as code-copied label cards

- **Status:** Accepted
- **Date:** 2026-10-04
- **Deciders:** Shabbir (approved the six decisions below on 2026-10-04) + Claude as advisor
- **Implements:** ADR-0005 (deterministic agrochemical safety). Reuses the Phase 5 pattern of ADR-0015 (a fail-closed reference table that code reads, a model that explains, code that checks) and the ADR-0012 rule (a source's content needs a human check, not just a licence).

## Context
CLAUDE.md rules 1 and 2: the model never invents a dose or a waiting period, and the check that enforces it runs after the model. Phase 4 shipped an interim regex guard for that. Phase 6 had to turn it from a stop-gap into a guarantee.

Measured on 2026-10-04 (`evals/chemical_guard_eval.py`, the Phase 4 patterns alone): of 47 adversarial dose or waiting-period phrasings, **12 were blocked and 35 reached the farmer**: "2 tsp per litre", "0.1% solution", "wait 21 days before you harvest", "प्रति एकड़ 250 मिली", "pump me 30 gram daalein", "thirty five grams per pump". The Phase 4 claim "0 doses reached the farmer" was true for the 55-question eval set and for nothing wider. Regex alone cannot be complete; the design therefore stops relying on it as the only barrier.

Data: the authoritative sources are CIB&RC documents on ppqs.gov.in (the registered-products pages and the lists of banned, refused and restricted pesticides). Automated fetches get a 403 (CLAUDE.md section 11). Search-result snippets about them are not reliable enough to enter a safety table (the same lesson as the FAO-56 tables in ADR-0015). So the data is acquired and verified by a human, and the system ships fail-closed.

## Decisions
1. **Two parts, in this order.** 6a: banned-molecule guard + hardened dose guard (no dose data needed). 6b: a lookup of verified label rows, shown as a structured card. A whole CIB&RC ingest is rejected: it cannot be verified row by row.
2. **Banned-molecule guard** (`app/safety/chemical_guard.py`, data `data/denylists/`). Runs in `finalize_advisory` after the model. A listed molecule named in the farmer's question, the model's text or a shown quote makes the answer abstain with `abstained_because: banned_molecule` and a code-authored bilingual message; the model's text is never shown. Only an injection refusal outranks it. **Every listed entry blocks, verified or not.** `status` changes only the wording: a verified entry may say "banned / restricted / refused registration in India (source, date)"; an unverified one says only that AgriAI cannot advise, because claiming a legal status nobody has checked is itself misinformation, while blocking a legal product costs one answer. Matching is by name (case and Unicode folded, whole words, Hindi, one-letter slips in names of 7+ letters). The 7 shipped entries are seeds from the author's recollection, all unverified with category `unclassified`.
3. **The dose guard becomes the permanent backstop and gets a second layer** (`app/safety/interim_dose_guard.py`). (a) The patterns were widened by the measurement above (household measures, percentages, ppm, `a.i.`, "per acre 500 g", waiting-period wording, spelled-out quantities, Hindi and Hinglish): 47 / 47 blocked, from 12. (b) New grounded-number rule: in any sentence about applying a chemical, **every number in the model's prose must come from the farmer's question, the farm record, the weather, a computed water balance or a code-authored message, never from a retrieved passage.** A wording no pattern knows still carries a number, and that number has no legitimate source. The corpus's trial rates stay unusable for advice.
4. **Doses reach a farmer only as a label card** (6b). A new response field `agrochemical_label` holds entries copied by code from a verified table (`data/agrochemical/major-uses-v1.json`, `app/safety/agrochemical_lookup.py`). The model never sees the numbers (its tool result says a card will be shown and lists only molecule, crop, pest), so it has nothing to leak, and any dose-shaped prose from it is blocked. A card is shown only on an answer, never on an abstention. Each card says it summarises CIB&RC "Major Uses" and that the product pack label is the legal source.
5. **The reference table is fail-closed**, like the crop table: a row is used only when verified by a named person with a source per row (document, date, page), every dose-relevant value present and in range, a waiting period present, and its molecule not on the denylist (a banned molecule is never returned even if someone entered a verified row for it). No row ships. Until a human adds verified rows the lookup answers `no_verified_entry` and the system abstains with the existing dose message.
6. **Tool gating by vocabulary.** `lookup_agrochemical` is offered to the model only when the question contains chemical vocabulary (spray, pesticide, dose, दवा, छिड़काव, a listed molecule, ...), to keep its ~150 tokens off every other question (Groq's free tier is the binding constraint).
7. **Data as repository files, not a database table.** This departs from `docs/database/schema.md` (an `agrochemicals` table). Files make every row's verification a reviewable Git diff and need no migration or service-role write path. Move to a table when the data outgrows a file.

## Consequences
- **Positive:** a dose cannot reach a farmer as model prose in any phrasing that carries a digit, a number word, or a known unit, and a banned molecule cannot be advised on; both are measured by an offline adversarial eval that needs no quota and is committed with its result.
- **Trade-offs and limits (stated so nobody reads more into the guarantee than it holds):**
  - The banned guard is a lexicon. A brand name, synonym or Hindi spelling not in `aliases` is **not** detected (3 declared gaps in the eval: a Hindi brand spelling, a chemical synonym, a vague quantity with no number or unit).
  - The grounded-number rule can block harmless text: a sentence about applying a product that carries a number the farmer did not give. That fails safe. It may raise the dose-guard abstention rate in RAG answers that describe a trial's protocol. A proxy run on 2026-10-04 (the 31 answerable questions' **reference answers** as if they were the model's draft, not captured drafts) blocked 0 of 31, the same as the old guard. Still measure with `evals/replay_finalize.py` on the captured Phase 4 drafts (no quota) before relying on the Phase 4 baseline.
  - Seed denylist entries are recollection, not data. State-level bans are not covered.
  - "Major Uses" is a summary; the pack label is the legal source and the card says so.
  - The eval measures the phrasings this project thought of. An unthought-of one is exactly what it cannot count.
- **Needs a human:** read the CIB&RC lists and fill both data files (`data/denylists/README.md`, `data/agrochemical/README.md`); until then banned wording stays generic and no label card can appear.

## Verification
`tests/test_dose_guard_adversarial.py`, `tests/test_chemical_guard.py`, `tests/test_agrochemical_lookup.py`, `tests/test_agent_agrochemical.py` (no LLM); `evals/chemical_guard_eval.py` (47 dose, 10 banned, 16 benign, 3 declared gaps; result in `evals/results/chemical-guard-2026-10-04.md`); mutation checks on the guards and on finalize.

## Sources
- CIB&RC / PPQS portal: https://ppqs.gov.in/divisions/cib-rc/registered-products (existence and location only, from search results on 2026-10-04; not fetched: automated access is refused).
- PIB release "Banning of Pesticides": https://www.pib.gov.in/PressReleaseIframePage.aspx?PRID=1896140&reg=48&lang=2 (not read in full; counts quoted by secondary sites were not used).

## Links
ADR-0005, ADR-0012, ADR-0014, ADR-0015, `data/denylists/README.md`, `data/agrochemical/README.md`, `apps/api/app/safety/`, `evals/chemical_guard_eval.py`.
