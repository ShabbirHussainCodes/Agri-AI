# data/denylists/

Molecules AgriAI must never advise on (CLAUDE.md rule 2, ADR-0016). Read **only** by deterministic code (`apps/api/app/safety/chemical_guard.py`). The LLM never reads or writes this.

## What a listed molecule does

Any listed molecule found in the farmer's question, the model's answer or a quoted passage makes the answer abstain (`abstained_because: banned_molecule`) and the farmer reads a code-authored bilingual message instead. **This holds for every entry, verified or not**: blocking advice about a molecule that turns out to be legal costs a farmer an answer, while advising on a banned one is harm, so an unlisted or unverified-but-listed molecule errs on the safe side.

What `status` changes is only the **wording**:

- `verified` (with `category`, `verified_by`, `verified_on`, `source_ref`): the message may say "banned / restricted / refused registration in India (CIB&RC list, ...)".
- `unverified`: the message says only that AgriAI cannot advise on it and sends the farmer to the product label and the KVK. It never claims a legal status, because saying "banned" about a legal product is misinformation.

## Status today

The 7 entries shipped are **seeds written from the author's recollection**, all `unverified`, category `unclassified`. Nobody on this project has read the official list yet.

## What to do (one browser session)

1. From ppqs.gov.in (CIB&RC section, "Registered Products" and the lists of banned / refused / restricted pesticides) download the **current** documents. The site refuses automated fetches (CLAUDE.md section 11), so do it in a browser. Put the PDFs in `data/agrochemical/_raw/` (gitignored). Check each document's licence and note its date.
2. For each molecule in the official **banned**, **refused** and **restricted** lists add an entry: `molecule` (lower-case English common name), `aliases` (spelling variants, common brand names, Hindi names), `category`, and `note` for any condition (for example "only by approved operators").
3. For every entry you checked against the document set `status: "verified"`, `verified_by`, `verified_on` and `source_ref` (document, date, page or serial number). `apps/api/tests/test_chemical_guard.py` rejects a verified entry with a missing field.
4. Central list only. State-level bans differ and are not covered (ADR-0005).
5. Restart the API (the file is cached per process), run `pytest apps/api/tests/test_chemical_guard.py`.

## Known gaps (stated, not hidden)

- Matching is by name: a molecule sold under a brand name that is not in `aliases` is **not** detected. The adversarial eval (`evals/chemical_guard_eval.py`) measures this, and the list only gets better by adding aliases.
- A name misspelled by one letter is still matched (words of 7+ letters), but a different spelling of a Hindi name may not be.
