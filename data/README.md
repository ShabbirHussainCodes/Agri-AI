# data/

Version-stamped reference data read **only** by the deterministic safety layer. The LLM never reads or writes these.

- `agrochemical/` — the CIB&RC "Major Uses of Pesticides" table, parsed to a structured, version-stamped form (e.g. `cibrc-major-uses-2025-08.csv`). Columns: molecule, formulation, crop, pest, dose_ai, dose_formulation, dilution_l, waiting_period_days, label_date, source. Raw source PDFs go in `_raw/` (gitignored).
- `denylists/` — banned / restricted molecules, central and state, with `notified_on` and `source`.

**Sourcing note:** obtain a current CIB&RC edition from ppqs.gov.in (automated fetch 403s; a known mirror is dated 2012 — do not ship the 2012 data). Stamp the version and set `AGRIAI_AGROCHEM_TABLE_VERSION`.

See `docs/decisions/ADR-0005-deterministic-agrochemical-safety.md`.
