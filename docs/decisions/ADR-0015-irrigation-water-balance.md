# ADR-0015: Irrigation advice is a deterministic FAO-56 water balance; the model explains, code checks

- **Status:** Accepted
- **Date:** 2026-10-04
- **Deciders:** Shabbir (approved the six decisions below on 2026-10-04) + Claude as advisor
- **Extends:** ADR-0006 / ADR-0013 (evidence-typed response, code-authored provenance). Applies ADR-0012 (a source's content needs a domain check, not just a licence) to agronomy reference numbers.

## Context
"Should I water my wheat today?" is the most common farm-specific question and the one the Phase 2 agent could only answer by improvising from a 3-day rain forecast. CLAUDE.md rule 7 says irrigation need (ET₀ − rainfall) is arithmetic and belongs in code; the LLM only explains.

The arithmetic is small (FAO-56 root-zone depletion bucket). The risk is in its **inputs**: crop coefficients, stage lengths, rooting depth, depletion fraction and soil water capacity are numbers that a wrong row turns into confident wrong advice with the authority of "computed". Search-engine snippets of the FAO-56 tables were tried on 2026-10-04 (the FAO and Open-Meteo hosts were blocked in the build environment) and were unusable: they mixed rows (sweet corn for maize) and disagreed with each other. That is the ADR-0012 failure mode again.

## Decisions
1. **Method: FAO-56 single-Kc root-zone depletion bucket**, in `app/agronomy/water_balance.py`. ET₀ is the FAO-56 Penman-Monteith value Open-Meteo publishes (`et0_fao_evapotranspiration`, mm/day, grass reference); the balance is ours. Rejected: a rain − ET₀ ledger (cannot say *when*), and Open-Meteo's modelled soil moisture alone (a coarse-grid weather-model estimate that does not represent irrigation).
2. **Reference table is fail-closed** (`data/crop_water/crop-water-v1.json`, `app/agronomy/crop_water.py`).
   - Three crops (wheat, tomato, maize) and three soil classes in the farmer's words (`sandy` retili, `loamy` domat, `clayey` chikni/kali). Any other crop answers `crop_not_supported`. Paddy is excluded on purpose: it is a flooded system and this method does not apply to it the same way (to be confirmed by the reviewer).
   - A row is used **only if** `status == "verified"` with `verified_by`, `verified_on`, a `sources` entry per value group, every value present and in range, and `kc_mid ≥ kc_ini, kc_end`. All rows ship **unverified**, so until a human fills and verifies them the engine answers `cannot_assess` with a reason. The checklist is `data/crop_water/README.md`.
   - Policy for ranges (reviewer may veto): where FAO-56 gives a range, take the end that makes the alert come **earlier** (smaller root depth, smaller available water). Irrigating a little early costs water; irrigating late costs yield.
3. **Starting point.** The soil is assumed full at an *anchor*: the sowing day, or the most recent irrigation logged **without an amount** (assumed to refill the root zone). An irrigation logged with `details.depth_mm` is applied as that amount. The anchor must lie inside the observed weather window (Open-Meteo `past_days` allows up to 92); otherwise the answer is `cannot_assess: no_anchor_in_window`. This makes the activity log load-bearing, which is the product's point (per-farm persistent state), at the cost that an older crop with no logged irrigation gets no verdict.
4. **Response contract.** `AdvisoryResponse.water_balance` (new, typed `WaterBalanceResult`, `null` when the tool did not run) carries the computed numbers. It is a new evidence type: not `live_data` (measured) and not `structured_data` (the farm record), but derived by code from both plus a reference table. `DraftAdvisory.irrigation_verdict` (new) is the model's one-word claim about it. The weather source attribution (Open-Meteo, CC BY 4.0) travels in `water_balance.data_source`.
5. **What code guarantees** (`app/safety/irrigation_guard.py`, applied in `finalize_advisory` only when a `water_balance` exists, v1 scope):
   - `cannot_assess` → the farmer gets a code-authored bilingual message for the reason (it says what to do: add the soil type, log the last irrigation, ...), and `abstained = true`, `abstained_because = <reason>`. The model's text is not shown. Every other abstention, including the model's own and `insufficient_evidence`, yields to this specific message; only an injection refusal or a dose refusal keeps its own.
   - `irrigate_now` / `wait` → the model's `irrigation_verdict` must equal the code's, and every number in its text must appear in the evidence it was given (farm record, weather, water balance, validated quotes, the farmer's own question). A mismatch or an ungrounded number replaces the text with a code-authored message built from the computed numbers, and the answer stays an answer.
   - The model claims `irrigate_now` / `wait` without any computation → abstain `irrigation_verdict_unsupported`.
   - The irrigation tool itself fails (a broken reference table, an unexpected exception) → the loop records `cannot_assess` with reason `irrigation_unavailable`, so the farmer is told the calculation is unavailable and the model cannot fill the gap with advice of its own. The exception text (it can contain a file path) is logged, never shown to the model.
   - Whenever a result exists the model's verdict must equal the code's, so claiming `not_applicable` does not dodge the check. When no result exists, irrigation advice phrased without a verdict claim cannot be detected: `irrigation_verdict` is self-reported, like `evidence_basis`.
   - Digits only: a number spelled out in words is not checked.
   - If the model abstains for its own reason (say `out_of_corpus`) on an irrigation question that code could answer, the model's abstention stands: code only ever makes an answer more cautious. The eval counts how often that happens.
   - Output is in **mm only**. The interim dose guard (CLAUDE.md rule 1) would withhold "litres per hectare" and "N days before harvest", which are not doses; staying in mm avoids the false positive.
6. **Tool.** A new LLM-gated read tool `get_irrigation_status` (no parameters, farm server-bound, like `get_weather`). `get_weather` is untouched so the recorded Open-Meteo request in the Phase 2 cassette stays byte-identical. A question that names a crop other than the farm's active crop gets `cannot_assess: question_crop_differs`, so a tomato question is never answered with the wheat balance.

**Decision rule** (agreed before any measurement):
- `irrigate_now` iff the depletion at the start of today, after rounding to 0.1 mm, is ≥ RAW (rounded the same way). Only observed rain and logged irrigation count.
- `wait` otherwise. `days_to_raw` is the first forecast day (0 = today) whose end reaches RAW at forecast ET₀, with **no forecast rain credited**, or `null` if not within 7 days. Forecast rain is shown separately.
- `cannot_assess` for any missing or untrustworthy input, with a reason code.

## Known limits (stated so nobody reads more into a verdict than it holds)
Direction of the error is given where it is known.
- Constant root depth for the whole season: early-season soil water capacity is overestimated, so a young crop is alerted **later** than it should be.
- The depletion fraction is not corrected for high evaporative demand (FAO-56 gives a correction; not applied): alert **later** on hot days.
- All rain counts, no runoff: **later** after heavy rain on slopes (Mandla is hilly).
- Forecast rain is not credited: alert **earlier** than needed when rain is coming.
- ET₀ and rain are gridded model values, not measurements from this field. The Kc table values assume a reference climate and are not adjusted.
- Stage lengths are fixed days from sowing, not scaled to a variety or season.
- One active crop per farm is assessed (the most recently sown). Two crops on one farm are not handled.
- "Today" is the date in the farm's local time as reported by Open-Meteo (`utc_offset_seconds`). `farm_context.days_since_sowing` still uses the server date, so the two can differ by one day in the early hours IST. Not fixed here.

- A question that mixes irrigation with something else ("will it rain, and should I spray?") gets the whole answer replaced when the irrigation part is `cannot_assess`, if the model called the irrigation tool for it. The Turn A prompt steers weather and spray questions to `get_weather`; the eval has no mixed scenario yet.

## Consequences
- **Positive:** the main farm-specific question gets a reproducible answer that the model cannot change; wrong inputs cannot slip in unnoticed (fail-closed table); the contract is changed now, before any frontend exists.
- **Trade-offs:** nothing works end to end until a human verifies the table (about 33 numbers read from FAO-56); older crops with no logged irrigation get `cannot_assess`; the number check can withhold a good answer on a false positive (fail-safe, measured in the eval).
- **Scope additions this needed:** `farms.soil_texture` (migration `20261004120000`) and `PATCH /farms/{id}`, because without an update route existing farms could never gain a soil type or a location and would answer `cannot_assess` forever. The remote `agriai-db` needs the migration before use.
- **Not decided here:** extending the number-grounding check to every answer (it would change Phase 4 behaviour; measure first), crediting forecast rain, root-depth growth over the season, Open-Meteo soil moisture as a cross-check, weather caching.

## Verification
- Hand-computed golden cases, invariants and mutation checks: `tests/test_water_balance.py`. Table fail-closed behaviour: `tests/test_crop_water.py`. The guard: `tests/test_irrigation_guard.py`. No LLM, no network.
- `app/agronomy/sanity_report.py` prints what a filled table implies (season ETc at a given ET₀, TAW, RAW) for the ADR-0012 domain check. It ships no acceptable range.
- Agent-level behaviour is measured on a separate eval bucket with frozen weather and a **synthetic** reference table. It measures the pipeline (verdict agreement, grounded numbers, abstention on missing inputs, zero doses), **not** agronomic accuracy (CLAUDE.md rule 4).

## Sources
- FAO Irrigation and Drainage Paper No. 56 (Allen et al., 1998), chapter 8: the depletion balance and the stress coefficient were seen quoted in search results on 2026-10-04; the primary page `https://www.fao.org/4/x0490e/x0490e0e.htm` could not be fetched from the build environment. Check Eq. 82–85 against it.
- Open-Meteo: `et0_fao_evapotranspiration` (mm, FAO-56 Penman-Monteith, grass reference), `forecast_days` up to 16, `past_days` 0–92, free API for non-commercial use under CC BY 4.0 (search results, 2026-10-04; `docs/integrations/external-integrations.md`). Proven against the live API on 2026-10-04 (one call from the owner's machine: 99 daily rows, 2026-07-04 to 2026-10-10, so `past_days=92` plus `forecast_days=7` is accepted and matches the engine's window).

## Links
ADR-0006, ADR-0012, ADR-0013, ADR-0014, `data/crop_water/README.md`, `apps/api/app/agronomy/`, `apps/api/app/safety/irrigation_guard.py`, `docs/ai/agent-design.md`.
