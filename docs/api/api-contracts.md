# API Contracts

> FastAPI. One Pydantic model serves triple duty (LLM schema · response model · OpenAPI). These are the *proposed* Phase-1+ contracts; keep them in sync with implementation. Auth: Supabase-issued JWT, verified server-side against the project JWKS. All routes require auth unless noted.

## Conventions

- Base path `/api/v1`. JSON. Errors: `{ "error": { "code", "message", "field?" } }` with a helpful, non-vague message.
- `routers/` contain no business logic — they validate, call a `service`, and return.
- Timestamps ISO-8601 UTC. IDs are UUIDs.

## Auth

Handled by Supabase Auth on the client; the backend only **verifies** the JWT (JWKS, ES256, check `aud`/`exp`, extract `sub` → profile). We write the verification middleware ourselves (learning value); we do not roll our own token issuance.

## Farm & onboarding

| Method | Path | Body → Response |
|---|---|---|
| POST | `/farms` | `{name, lat?, lon?, area_ha?, district?, state?, soil_texture?}` → `Farm`. `soil_texture` is `sandy` (retili) · `loamy` (domat) · `clayey` (chikni/kali); lat/lon are range-checked |
| GET | `/farms` | → `Farm[]` (only the caller's) |
| GET | `/farms/{id}` | → `Farm`; a farm that is not the caller's is a 404 (ADR-0017) |
| PATCH | `/farms/{id}` | any of `{name, lat, lon, area_ha, district, state, soil_texture}` → `Farm`. Only the fields sent change; an explicit `null` clears a nullable field; an empty body is a 422; a farm that is not the caller's is a 404 (ADR-0015: a farm created without a location or soil type could otherwise never gain one) |
| POST | `/farms/{id}/crops` | `{crop_id, variety, sowing_date}` → `FarmCrop` (stage computed) |
| GET | `/farms/{id}/timeline` | → chronological `activities` + `advisories` + `disease_scans` |

## Activities (write → confirmation required)

| Method | Path | Notes |
|---|---|---|
| POST | `/farm-crops/{farm_crop_id}/activities` | `{type, occurred_on, details}` → `Activity`. When proposed by the agent, requires explicit user confirmation before this is called. |

## Ask (the agent)

| Method | Path | Body → Response |
|---|---|---|
| POST | `/farms/{id}/ask` | `{question, language?}` (question 1–1000 chars; `language` is `"hi"` or `"en"`, optional: it asks the model to write in that language, see `docs/ai/ui-language-hint.md`; anything else is a 422) → `AdvisoryResponse`. Saved to `advisories`. **429** `{error:{code:"ask_limit_reached", scope:"user"\|"global", message}}` (bilingual) when the rolling 24-hour cap is reached, before any LLM call (ADR-0017). A farm that is not the caller's is a 404. |
| GET | `/farms/{id}/advisories` | → `AdvisoryRecord[]`, newest first: `{id, farm_id, question, response, abstained, created_at}` |

`AdvisoryResponse` (evidence-typed):
```
{
  structured_data: {...},
  live_data: {...} | null,
  water_balance: {...} | null,           // ADR-0015: computed by code, null unless get_irrigation_status ran
  agrochemical_label: [ {...} ],         // ADR-0016: verified label cards copied by code; [] on any abstention
  retrieved_evidence: [ { chunk_id, source_org, doc_title, doc_type, published_year, page, licence, url, quote } ],
  model_inference: string,
  recommendation: string,
  confidence: number | null,
  abstained: boolean,
  abstained_because: string | null,
  citations_valid: boolean,
  limitations: string                    // code-authored bilingual note, "" for almost every answer (see below)
}
```

Since Phase 4 (ADR-0013) this object is assembled by code, not written by the model: the model writes a `DraftAdvisory` (reasoning, recommendation, `{passage, quote}` citations); code copies the farm record, weather and every piece of source metadata, validates each quote against the passage it names, and decides abstention (`abstained_because`: the model's own reason, or `insufficient_evidence` · `empty_answer` · `invalid_citation` · `no_valid_citation` · `crop_not_covered` (ADR-0014) · `no_verified_dose_source` · `banned_molecule` (ADR-0016) · `answer_generation_failed` (the model's output was rejected twice; code-written message, see below)).

**Retry and `answer_generation_failed` (2026-10-06).** If the provider rejects the model's output, or Turn B returns nothing parseable, the loop retries once, then returns HTTP 200 with `abstained: true`, `abstained_because: "answer_generation_failed"` and a code-written bilingual message ("could not prepare an answer just now ... ask again in a little while, or ask your KVK"). Evidence, label cards and `limitations` are empty; a `water_balance` that code had already computed is kept. Quota, authentication and network failures are not retried and keep the 502 `agent_unavailable` envelope. Such an answer is saved and counts against the daily cap.

**Limitations (2026-10-06).** `limitations` is a code-written note (Hindi paragraph, blank line, English paragraph; never the model's) about what an answer does *not* rest on. It is set only when the question names a crop, the answer is not an abstention, no `water_balance` and no label card are present, and no document evidence is shown: the answer then rests on the farm record (and weather) alone, and the note says that no verified document was used and points to a KVK. It is `""` otherwise. Advisories saved before the field existed have no `limitations` key; clients must treat a missing value as empty. The Hindi wording has had no native-speaker review. Days-since-sowing in `structured_data` counts on the farm's calendar (`AGRIAI_LOCAL_UTC_OFFSET_MINUTES`, default 330), not on the server's UTC date.

**Chemicals (Phase 6, ADR-0016).** A pesticide dose or waiting period reaches the farmer only inside `agrochemical_label`: a list of cards (`row_id`, `molecule`, `formulation`, `crop`, `pest`, `dose_formulation` + `dose_formulation_unit` (`g` or `ml`) per hectare, optional `dose_ai_g_per_ha` and `dilution_l_per_ha`, `waiting_period_days`, `label_date`, `source_ref`, `table_version`, and a bilingual `text`) that code copied from a verified table row. The model never writes those numbers, so `recommendation` never contains a dose. A card says it summarises CIB&RC "Major Uses" and that the label on the product pack is the legal source. It appears only on an answer. If the farmer's question, the model's text or a shown quote names a molecule on the denylist, the answer abstains with `abstained_because: banned_molecule` and a code-authored message (verified entries may name the legal status and source; unverified ones never claim one). `recommendation` and `model_inference` are never blank: when there is no model text to show, code supplies a bilingual (Hindi + English) message for the abstention reason.

**Irrigation (Phase 5, ADR-0015).** `water_balance` is a third kind of evidence next to `live_data` (measured) and `structured_data` (the farm record): numbers *computed* by code from both plus a reference table. Fields: `verdict` (`irrigate_now` · `wait` · `cannot_assess`), `reason` (set when `cannot_assess`), `as_of`, `crop`, `soil_texture`, `table_version`, `days_since_sowing`, `stage`, `kc_today`, `depletion_mm`, `raw_mm`, `taw_mm`, `days_to_raw` (first forecast day, 0 = today, whose end reaches `raw_mm`; null = not within the horizon), `forecast_et0_mm`, `forecast_rain_mm` (context only, never counted), `anchor_date`, `anchor_kind`, `last_irrigation_on`, `assumptions`, `data_source` (Open-Meteo attribution). All amounts are in mm. The model writes only the explanation and one word, `irrigation_verdict`, which code compares with the computed verdict. Extra `abstained_because` values: `irrigation_verdict_unsupported`, and, for a `cannot_assess` result, its `reason` (`no_location` · `no_active_crop` · `question_crop_differs` · `crop_not_supported` · `crop_reference_unverified` · `soil_texture_missing` · `soil_reference_unverified` · `not_sown_yet` · `past_season_length` · `no_weather_data` · `weather_gap` · `weather_unavailable` · `irrigation_unavailable` (the tool itself failed) · `no_anchor_in_window`). A model answer whose verdict or numbers disagree with the computed result is replaced by a code-authored message and stays an answer (`model_inference` says `Model text replaced by code: ...`).

An irrigation logged through `POST /farm-crops/{id}/activities` with `type: "irrigation"` may carry `details.depth_mm`; without it the balance assumes the root zone was refilled completely.

## Voice

| Method | Path | Notes |
|---|---|---|
| POST | `/speech/transcribe` | multipart audio → `{transcript, language, low_confidence}`. The client always shows the editable transcript before sending it to `/ask`. |

## Crop image diagnosis (Phase 7, ADR-0018)

| Method | Path | Notes |
|---|---|---|
| POST | `/farms/{id}/scans` | `multipart/form-data`: `image` (a JPEG, PNG or WebP, at most 8 MB) and optional `language` (`hi` or `en`, asks the answer model to write in it, like `/ask`). Returns `DiagnosisResponse`. A photo that fails the quality gate is a normal **200** with `outcome: "rejected_quality"` and a retake tip: it is neither saved nor counted. Upload errors use the error envelope with a bilingual message: **400** `empty_upload`, **413** `file_too_large` / `image_too_large`, **415** `unsupported_image_type` (type read from the bytes, never from the file name or Content-Type), **422** `unreadable_image` / `invalid_language`. **429** `scan_limit_reached` `{scope: "user"\|"global"}` before any model call. A farm that is not the caller's is a 404. |
| GET | `/farms/{id}/scans` | `ScanRecord[]`, newest first: `{id, farm_id, image_path, outcome, abstained_because, response, farmer_feedback, created_at}`. `response` is the `DiagnosisResponse` exactly as the farmer received it, kept as a plain object. |
| POST | `/scans/{id}/feedback` | `{agrees: bool, confirmed_label?: string}`; `confirmed_label` must be one of the classifier's class strings (422 `unknown_label` otherwise). The seed of a field dataset; changes nothing about what the farmer was told. |
| DELETE | `/scans/{id}` | 204. Removes the row and the stored photo. A scan that is not the caller's is a 404. |

`DiagnosisResponse` (code-built, like `AdvisoryResponse`; `apps/api/app/schemas/scan.py`):
```
{
  outcome: "rejected_quality" | "abstained" | "diagnosis",
  abstained_because: string | null,   // quality_rejected, out_of_distribution, low_confidence, crop_not_supported,
                                      // crop_not_validated, not_a_plant_photo, model_disagreement, crop_differs_from_farm, vision_unavailable,
                                      // vision_not_calibrated, answer_generation_failed, or any /ask reason from the answer step
  detail: string | null,              // a stable sub-reason, e.g. "crop_differs" for a model_disagreement
  message: string,                    // code-written, bilingual: the retake tip or the reason no disease is named; "" for a diagnosis
  quality: { passed, reasons[], thresholds_version, sharpness, mean_luma, vegetation_fraction, width, height },
  candidates: [ { label, crop, condition, name_en, name_hi, name_hi_status, probability, leading, second_opinion_agrees } ],  // top-3, only for a diagnosis; the agreed one first
  band: { name: "high"|"medium"|"low", observed_accuracy, n, measured_on } | null,   // the ONLY confidence shown
  model_saw: { plant_part, crop, condition, symptoms } | null,   // what the vision model reported, after the dose / banned-molecule guards
  advisory: AdvisoryResponse | null,  // a diagnosis's evidence-typed answer: recommendation, label card, cited documents, limitations
  note: string,                       // always set on a diagnosis: an automatic check, not an expert's confirmation
  versions: { classifier, calibration, label_map, vision_model | null },
  scan_id, image_path, created_at     // set by the router after the row is saved
}
```
`candidates[].probability` is the classifier's calibrated score for the API and the evals; the app never shows it as a percentage. The only confidence shown to a farmer is `band`, with the accuracy that band actually had on field photos in the project's own measurement (`data/vision/calibration-v1.json`, `evals/results/vision-*.md`). A dose reaches a farmer only inside `advisory.agrochemical_label`, copied by code from a verified row for the diagnosed crop and condition; the model never sees it.

## Market (modular, secondary)

| Method | Path | Notes |
|---|---|---|
| GET | `/market/advice` | `?commodity=&district=&days=` → `{series, percentile_band, signal, explanation, disclaimer}`. Statistics in code; LLM only explains. Never blocks core routes. |

## Reminders & push

| Method | Path | Notes |
|---|---|---|
| POST | `/farms/{id}/reminders` | write → confirmation required |
| POST | `/push/subscribe` | store Web Push subscription |

## Validation & limits

Every input is Pydantic-validated. Uploads: size + MIME + image-decode check + server-side resize before anything else. Per-user rate limiting on `/ask`, `/scans`, `/speech`. See `docs/security/security-model.md`.
