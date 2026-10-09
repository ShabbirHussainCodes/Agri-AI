# data/denylists/

Molecules AgriAI must never advise on (CLAUDE.md rule 2, ADR-0016). Read **only** by deterministic code (`apps/api/app/safety/chemical_guard.py`). The LLM never reads or writes this.

## What a listed molecule does

Any listed molecule found in the farmer's question, the model's answer or a quoted passage makes the answer abstain (`abstained_because: banned_molecule`) and the farmer reads a code-authored bilingual message instead. **This holds for every entry, verified or not**: blocking advice about a molecule that turns out to be legal costs a farmer an answer, while advising on a banned one is harm, so an unlisted or unverified-but-listed molecule errs on the safe side.

What `status` changes is only the **wording**:

- `verified` (with `category`, `verified_by`, `verified_on`, `source_ref`): the message may say "banned / restricted / refused registration in India (CIB&RC list, ...)".
- `unverified`: the message says only that AgriAI cannot advise on it and sends the farmer to the product label and the KVK. It never claims a legal status, because saying "banned" about a legal product is misinformation.

## Status today (2026-10-09, `banned-central-v2`)

92 entries transcribed from the CIB&RC list **updated on 31.07.2026** (`data/agrochemical/_raw/banned.pdf`, 6 pages; the 7 earlier memory seeds are all on it and were merged). Each `source_ref` gives the section, serial number and PDF page. Checked against the PDF by Shabbir Hussain on 2026-10-09.

| Section of the PDF | Entries | `category` |
|---|---|---|
| I.A Banned for manufacture, import and use | 49 | `banned` |
| I.B Banned for use, manufacture for export continued | 1 new (Nicotin Sulfate); Captafol, Dichlorvos, Phorate and Triazophos are already listed and carry a note | `banned` |
| I.C Withdrawn (S.O. 915(E), 2006) | 8 | stays `unverified` / `unclassified`: the schema has no "withdrawn" category, so these block without claiming a legal status |
| II Refused registration | 18 | `refused` |
| III Restricted for use | 16 | `restricted` |

Decisions and readings to know:

- **Restricted molecules are blocked as a whole** (decided 2026-10-09, following ADR-0016). Several are legal with crop-specific bans (for example Mancozeb is banned only on guava, jowar and tapioca), so AgriAI gives no advice or label card on them at all. A crop-aware restriction would be more precise and needs its own ADR.
- The PDF prints "Endosulfron"; read as **endosulfan** (Supreme Court WP(C) 213 of 2011), kept as an alias.
- "Dichlorovos" (I.A) and "Dichlorvos" (I.B) are one molecule; the first spelling is an alias.
- Aliases are only names printed in the PDF (Gamma-HCH, DBCP, EDB, PCNB, TCA, PDCB, Morestan, Phosvel, Phosdrin, Thiodemeton, Camphechlor), plus `chlorpyrifos`, the spelling the Major Uses tables use, and the seeds' earlier aliases. No brand names were added.

## What to do (one browser session)

1. From ppqs.gov.in (CIB&RC section, "Registered Products" and the lists of banned / refused / restricted pesticides) download the **current** documents. The site refuses automated fetches (CLAUDE.md section 11), so do it in a browser. Put the PDFs in `data/agrochemical/_raw/` (gitignored). Check each document's licence and note its date.
2. For each molecule in the official **banned**, **refused** and **restricted** lists add an entry: `molecule` (lower-case English common name), `aliases` (spelling variants, common brand names, Hindi names), `category`, and `note` for any condition (for example "only by approved operators").
3. For every entry you checked against the document set `status: "verified"`, `verified_by`, `verified_on` and `source_ref` (document, date, page or serial number). `apps/api/tests/test_chemical_guard.py` rejects a verified entry with a missing field.
4. Central list only. State-level bans differ and are not covered (ADR-0005).
5. Restart the API (the file is cached per process), run `pytest apps/api/tests/test_chemical_guard.py`.

## Known gaps (stated, not hidden)

- Matching is by name: a molecule sold under a brand name that is not in `aliases` is **not** detected. The adversarial eval (`evals/chemical_guard_eval.py`) measures this, and the list only gets better by adding aliases.
- A name misspelled by one letter is still matched (words of 7+ letters), but a different spelling of a Hindi name may not be.
