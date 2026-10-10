# data/agrochemical/

Verified label rows: the **only** way a pesticide dose or waiting period reaches a farmer (CLAUDE.md rule 1, ADR-0016). Read **only** by deterministic code (`apps/api/app/safety/agrochemical_lookup.py`). The LLM never reads or writes this, and never sees the numbers in it: the farmer gets a structured **label card** that code copies from a row.

## Status (2026-10-10): 11 rows, wheat and tomato

Transcribed from CIB&RC "Major Uses of Pesticides", Fungicides and Herbicides, **upto 31.03.2026** (PDFs in `_raw/`, gitignored), and checked against the page images. Checked against the PDFs by Shabbir Hussain on 2026-10-10. Any crop, pest or molecule not in these rows still answers "no verified label entry" and abstains (`no_verified_dose_source`).

| Crop | Pest | Products |
|---|---|---|
| tomato | early blight, late blight | Azoxystrobin 23% SC, Captan 75% WP |
| wheat | karnal bunt, brown rust, stem rust, yellow rust | Propiconazole 25% EC |
| wheat | phalaris minor | Clodinafop-propargyl 15% WP, Sulfosulfuron 75% WG |
| wheat | chenopodium album | Metsulfuron Methyl 20% WP |

How the rows were chosen (so the next person can repeat it):

- Only rows with **one printed formulation dose**, a **printed unit** (g or ml) and a **numeric waiting period**. Ranges ("450-600"), "%" doses and "-" waiting periods were skipped, because the table holds one number and nothing is converted or picked from a range.
- **No insecticide rows yet.** The Insecticides volume prints the unit only in the column header ("gm/ml"), not per row, so g versus ml would be a guess. Tomato fruit borer and wheat aphid therefore still abstain.
- No molecule on the denylist (restricted molecules such as Mancozeb are blocked as a whole, see `data/denylists/README.md`).
- Where the printed dilution is a range or carries a surfactant note, `dilution_l_per_ha` is left empty and the printed text is in `notes`.
- A row printed as "Early & Late blight" is split into two rows with the same values.
- Propiconazole 25% EC prints its formulation dose as "500gm" although an EC is a liquid; copied as printed.
- `pest_aliases` marked in `notes` (Hindi names such as अगेती झुलसा, पीला रतुआ, बथुआ, गुल्ली डंडा) were added for matching and are not printed in the PDF. A wrong alias can only show the right card for the wrong word, never change a number, but each was still checked.
- The PDF says it is compiled "for guidance and not for legal purposes": the card already tells the farmer that the label on the pack is the legal source.

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
