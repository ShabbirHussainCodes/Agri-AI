# data/crop_water/

Reference inputs for the Phase 5 irrigation water balance (ADR-0015). Read **only** by deterministic code (`apps/api/app/agronomy/`). The LLM never reads or writes this table.

## Status: every row is `unverified`, on purpose

The water-balance engine uses a row **only if** its `status` is `"verified"`, with `verified_by`, `verified_on` and a `sources` entry for every value group. Anything else makes the engine answer `cannot_assess` with a reason, so the farmer is told to ask a KVK instead of getting a computed-looking answer built on unchecked numbers.

Why not pre-fill from what a search engine returns? Tried on 2026-10-04 (the FAO and Open-Meteo hosts were blocked in the build environment, so only search snippets were available). The snippets disagreed with each other and used the wrong row for the crop: a sweet-corn row for "maize", and wheat values that did not match the winter/spring wheat rows. That is the ADR-0012 failure mode (right source, wrong row). Values go in only after a human reads the primary table.

A shorter, demo-sized version (Wheat + loamy soil, optional Tomato) with the exact table, row and column per field is in `FILL-CHECKLIST-demo.md`.

## What to fill in (one browser session)

Source for everything: FAO Irrigation and Drainage Paper No. 56 (Allen et al., 1998), published on fao.org. Table and chapter numbers below are from memory and search snippets, so **confirm each in the document itself**.

| Field | Where to read it | Notes / traps |
|---|---|---|
| `kc_ini`, `kc_mid`, `kc_end` | Table 12 (single crop coefficients) | Wheat has separate winter and spring rows: use the one that matches an Indian rabi crop and say which. Maize: field/grain, **not** sweet corn (its `kc_end` is very different). The table values assume a reference climate; FAO-56 gives an adjustment for `kc_mid`/`kc_end` in other humidity/wind conditions. v1 does not adjust. Write that in `notes`. |
| `stage_days` (`initial`, `development`, `mid`, `late`) | Table 11 (lengths of crop development stages) | The lengths are given per planting region/season. Pick the one closest to India or the farm's season and write it in `stage_length_basis`. If none fits, ask an agronomist or KVK: do not average. |
| `root_depth_m` | Table 22 (maximum effective rooting depth) | The table gives a range. v1 uses **one constant depth for the whole season**. Policy (ADR-0015): take the **lower end** of the range, so the alert comes earlier, not later. Note this in `notes`. |
| `p` | Table 22 (depletion fraction for no stress) | I believe the table value is for ETc of about 5 mm/day and FAO-56 gives a correction for other rates. v1 does not correct. Note it. |
| `theta_fc`, `theta_wp` (per soil class) | Table 19 (soil water characteristics by texture) | The table gives ranges per FAO texture class. Pick the FAO class that matches the farmer's word (retili / domat / chikni), put it in `fao56_class`, and use one rule for all three classes (policy: the lower end of the available-water range). Black cotton (kali) soils are clayey. |

For each crop, `sources` needs keys `kc`, `stage_days`, `root_depth_m` and `p`. For each soil, key `theta`. The value is free text such as `"Table 12, row 'Wheat, winter', as read 2026-10-xx"`.

Then set `status` to `"verified"`, `verified_by` to your name and `verified_on` to the date. `apps/api/tests/test_crop_water.py` rejects a verified row with a missing value, an out-of-range value, or `kc_mid` below `kc_ini` or `kc_end`.

## Sanity check (ADR-0012)

Reading the table is not enough. After filling a crop, print what its numbers imply and check that against a published figure for the same crop and region:

```
cd apps/api
python -m app.agronomy.sanity_report --et0 <mean ET0 in mm/day for the sowing season>
```

It prints, for every verified row, the season length, mean Kc, the season's total ETc at that ET0, and each soil's available water, TAW and RAW. Take `--et0` from the weather of the farm and season you are checking (Open-Meteo's `et0_fao_evapotranspiration`, averaged); there is no default on purpose. It ships no acceptable range, because an unsourced range would be the same kind of number this table avoids. If a result looks wrong, the row is wrong. Do not "correct" a value silently: write what you changed and why in `notes`.

## After editing

The API reads this file once per process and caches it, so **restart the API** after changing it. A file that fails validation is never half-used: the first irrigation question logs the error on the server and the farmer is told the irrigation calculation is unavailable (`irrigation_unavailable`): run `pytest apps/api/tests/test_crop_water.py` first, it loads the shipped file.
