# data/

Version-stamped reference data read **only** by the deterministic safety layer. The LLM never reads or writes these.

- `agrochemical/` — the CIB&RC "Major Uses of Pesticides" table, parsed to a structured, version-stamped form (e.g. `cibrc-major-uses-2025-08.csv`). Columns: molecule, formulation, crop, pest, dose_ai, dose_formulation, dilution_l, waiting_period_days, label_date, source. Raw source PDFs go in `_raw/` (gitignored).
- `denylists/` — molecules AgriAI must never advise on (`banned-central-v1.json`, central only). Every entry blocks; `status` only decides whether the message may name a legal status. Shipped entries are unverified seeds (ADR-0016, `denylists/README.md`).
- `agrochemical/major-uses-v1.json` — verified label rows, the only source of a dose or waiting period. Ships with no rows (ADR-0016, `agrochemical/README.md`).
- `crop_water/` — crop coefficients, stage lengths, rooting depth, depletion fraction and soil water capacity for the irrigation water balance (ADR-0015). Every row ships `unverified` and is ignored by the engine until a human verifies it against FAO-56; see `crop_water/README.md`.

**Sourcing note:** obtain a current CIB&RC edition from ppqs.gov.in (automated fetch 403s; a known mirror is dated 2012 — do not ship the 2012 data). Stamp the version and set `AGRIAI_AGROCHEM_TABLE_VERSION`.

See `docs/decisions/ADR-0005-deterministic-agrochemical-safety.md`.
