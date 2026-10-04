# data/agrochemical/

Verified label rows: the **only** way a pesticide dose or waiting period reaches a farmer (CLAUDE.md rule 1, ADR-0016). Read **only** by deterministic code (`apps/api/app/safety/agrochemical_lookup.py`). The LLM never reads or writes this, and never sees the numbers in it: the farmer gets a structured **label card** that code copies from a row.

## Status: no rows

The file ships empty on purpose. Until a person adds verified rows every dose question answers "no verified label entry" and the system abstains (`no_verified_dose_source`). That is the safe state, not a bug.

Do **not** fill it from search snippets, from memory, from the research trial in the corpus, or from a secondary summary (for example a university page): the same row-mixing that made the FAO-56 snippets unusable (ADR-0015) is far more dangerous here. A row is entered from the **primary document**, one row at a time, by a person who then reads it back against the page.

## What to do

1. Download the **current** CIB&RC "Major Uses of Pesticides" (and, if you want label-level checks, the product label) from ppqs.gov.in in a browser (the site refuses automated fetches). Put the PDF in `data/agrochemical/_raw/` (gitignored). Note the document's **date** and check its **licence**.
2. Start small: the crops of your demo farm (`wheat`, `tomato`, `maize`) and a handful of common pests, about 10 to 20 rows. A table of thousands of rows cannot be verified row by row.
3. If you attach the PDF to a Claude session, it can draft candidate rows with page references, all `status: "unverified"`. You then verify each one against the page.
4. Row fields:

| field | meaning |
|---|---|
| `id` | unique, e.g. `tomato-earlyblight-001` |
| `molecule` | lower-case common name, as in the document. A molecule on the denylist is never returned, even if you enter it |
| `molecule_aliases`, `pest_aliases` | other names farmers or the document use (Hindi names help) |
| `formulation` | as printed, e.g. `"Mancozeb 75% WP"` |
| `crop` | a **canonical crop key** from `apps/api/app/safety/crop_scope.py` (`CROP_LEXICON`), e.g. `tomato` |
| `pest` | lower-case, as in the document |
| `dose_formulation`, `dose_formulation_unit` | formulation dose per hectare and its unit, `g` or `ml` |
| `dose_ai_g_per_ha`, `dilution_l_per_ha` | optional, if the document gives them |
| `waiting_period_days` | whole days, 0 to 365. **Required**: a dose without its waiting period is never shown |
| `label_date`, `source_ref` | the document's date; document, page and serial number |
| `status`, `verified_by`, `verified_on` | set `verified` only after reading the row back against the page |

5. Restart the API (the file is cached per process) and run `pytest apps/api/tests/test_agrochemical_lookup.py`: a verified row with a missing or out-of-range value makes the file fail to load.

## What the farmer sees

A card with the formulation, the dose per hectare, the dilution if given, the waiting period, the source and date, and the sentence that this summarises CIB&RC "Major Uses" and that the **label on the product pack is the legal source**. State-level restrictions are not covered (ADR-0005).
