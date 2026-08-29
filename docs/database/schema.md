# Database Design

> Supabase Postgres (project `agriai-db`, `ap-south-1`), `pgvector` enabled. Row-Level Security on every user-owned table. SQL migrations live in `db/migrations/` and are checked in. This is the *proposed* model for Phase 1 — refine during implementation via migrations, not by editing history.

## 1. Why these entities

The farm record **is** the product, so the relational model is first-class, not an afterthought. Retrieval chunks live in the same database as farm data so metadata filtering is a plain SQL join and access control is one RLS story.

## 2. Core entities

### `profiles`
The farmer. `id` (= Supabase `auth.uid()`), `display_name`, `preferred_language` (`hi`|`en`), `phone` (optional), `created_at`. Minimal PII by design.

### `farms`
A farm belongs to a profile. `id`, `profile_id` (FK), `name`, `lat`, `lon` (geocoded once at registration, then stored — never re-geocoded), `district`, `state`, `agro_climatic_zone`, `area_ha`, soil card values (`soil_ph`, `soil_n`, `soil_p`, `soil_k`, nullable — farmer-entered, since there is no Soil Health Card API), `created_at`.

### `crops` (reference) and `farm_crops`
`crops` is a reference table (crop id, names in hi/en, default calendar hints). `farm_crops` is a specific planting: `id`, `farm_id` (FK), `crop_id` (FK), `variety`, `sowing_date`, `expected_harvest`, `status` (active/harvested), `created_at`. Growth stage is **computed** from `sowing_date`, never stored as a mutable field.

### `activities`
The timeline spine. `id`, `farm_crop_id` (FK), `type` (irrigation|fertiliser|spray|sowing|scouting|other), `occurred_on`, `details` (JSONB for type-specific fields), `source` (farmer|agent-confirmed), `created_at`. Written only via the confirmed `log_activity` path.

### `advisories`
A recorded AI interaction/outcome. `id`, `farm_id` (FK), `question`, `response` (the evidence-typed object as JSONB), `abstained` (bool), `created_at`. This is what makes the next answer context-aware and gives an audit trail.

### `disease_scans`
`id`, `farm_crop_id` (FK), `image_path` (Supabase Storage key), `top_candidates` (JSONB), `ood_score`, `quality_flags` (JSONB), `outcome` (JSONB — grounded recommendation or abstention), `farmer_feedback` (nullable — confirm/correct, future field dataset), `created_at`.

### `reminders`
`id`, `farm_id` (FK), `due_at`, `message`, `channel` (webpush|…), `status`, `created_at`. Written only via confirmed `create_reminder`.

## 3. Knowledge base (RAG)

### `documents`
`id`, `source_org`, `doc_title`, `doc_type`, `url`, `published_year`, `language`, `licence`, `ingested_at`.

### `chunks`
`id`, `document_id` (FK), `content`, `context_prefix` (v2 contextual retrieval), `embedding vector(384)` (v1; `vector(1024)`/`halfvec` in v2), `tsv tsvector` (generated), `crop_id` (nullable FK), `state`, `agro_climatic_zone`, `page_no`, `section_path`.
Indexes: HNSW on `embedding`, GIN on `tsv`, btree on the filter columns.

## 4. Reference / safety data

### `agrochemicals` (version-stamped)
`id`, `table_version` (e.g. `cibrc-major-uses-2025-08`), `molecule`, `formulation`, `crop`, `pest`, `dose_ai`, `dose_formulation`, `dilution_l`, `waiting_period_days`, `label_date`, `source`. **Only the deterministic layer reads this; the LLM never writes or invents rows.**

### `banned_molecules`
`id`, `molecule`, `scope` (central|state), `state` (nullable), `notified_on`, `source`. The denylist filter.

## 5. Market data

### `mandi_prices`
`id`, `commodity`, `variety`, `grade`, `state`, `district`, `market`, `arrival_date`, `min_price`, `max_price`, `modal_price`, `ingested_at`. Populated by the scheduled ingest job; statistics computed in code.

## 6. Security model at the DB level

- RLS on `profiles`, `farms`, `farm_crops`, `activities`, `advisories`, `disease_scans`, `reminders`: a row is visible/writable only to its owning `auth.uid()`.
- Knowledge, agrochemical, banned-molecule, and mandi tables are read-mostly reference data (service-role writes at ingest; authenticated read).
- Storage bucket `crop-photos` uses the same `auth.uid()` policy — a farmer sees only their own photos.

## 7. Indexing & free-tier note

Dimension is an architecture choice on a 500 MB / 500 MB-RAM free tier: 384-d for v1 keeps the index small; `halfvec` is the escape hatch at v2's 1024-d. Keep the corpus in the low-thousands-to-~15k chunks range for the free tier.
