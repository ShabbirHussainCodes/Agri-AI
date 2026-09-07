-- Phase 3: the RAG corpus tables (documents + chunks).
--
-- These are NOT farmer data. The corpus is shared reference knowledge that
-- every farmer's agent reads, so the per-farmer ownership RLS used in Phase 1
-- (farms / farm_crops / activities) would be wrong here. The right precedent
-- is public.crops (migration 20260829120004): RLS on, a single read-only
-- policy for `authenticated`, and NO write policy at all -- the corpus is
-- written only by the laptop ingest job using the service role, which
-- bypasses RLS entirely.
--
-- pgvector lives in the `extensions` schema (migration 20260830090000), so
-- the vector type and its operator class are schema-qualified below.

-- ------------------------------------------------------------------
-- documents: one row per ingested source document
-- ------------------------------------------------------------------
create table public.documents (
  id uuid primary key default gen_random_uuid(),

  -- Which entry in ingest/sources.yaml this came from (e.g. 'cgspace-cgiar').
  -- Deliberately plain text, not an FK: the licence register is a
  -- version-controlled file reviewed in Git, and corpus provenance should
  -- not depend on a mutable database row.
  source_id text not null,

  -- Repository handle, e.g. '10568/180614'. Unique, so re-running ingest
  -- cannot silently create a duplicate document.
  handle text unique,

  title text not null,
  publisher text,
  published_year integer,

  -- Governs how the agent may use the text (ADR-0006). A 'manual' is
  -- guidance; a 'journal_article' reports a trial and is evidence only --
  -- never a recommendation on its own.
  doc_type text not null check (doc_type in (
    'manual', 'journal_article', 'report', 'brief', 'book', 'factsheet', 'other'
  )),

  -- Exact licence string as shown on the item page, e.g. 'CC-BY-4.0'.
  -- Stored per document so an answer can always name its licence, and so a
  -- licence question can be audited without re-reading sources.yaml.
  licence text not null,
  url text not null,
  language text not null default 'en',

  -- Provenance: exactly which file produced these chunks. If the publisher
  -- replaces the PDF, the hash changes and we know to re-ingest.
  file_sha256 text not null unique,
  page_count integer,

  ingested_at timestamptz not null default now()
);

create index documents_source_id_idx on public.documents(source_id);

-- ------------------------------------------------------------------
-- chunks: one row per retrievable chunk
-- ------------------------------------------------------------------
create table public.chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,

  -- Position within the document. With document_id this makes re-ingestion
  -- idempotent (see the unique constraint at the end of the table).
  chunk_index integer not null,

  content text not null,

  -- Metadata as real columns, not JSONB (rag-design.md section 4), so it can
  -- be filtered and indexed cheaply.
  page_no integer,
  section_path text,
  language text not null default 'en',
  crop_id uuid references public.crops(id),

  -- Indian state or agro-climatic zone, when the source is specific to one
  -- (e.g. the Tamil Nadu tomato study). Plain text for now: there is no
  -- states reference table yet, and inventing one before the widening
  -- cascade (rag-design.md section 4) exists would be premature.
  state text,

  -- multilingual-e5-small is 384-dimensional (CLAUDE.md stack table).
  -- Nullable on purpose: a parse/chunk run can be inspected in the database
  -- before the embedding step has run.
  embedding extensions.vector(384),

  -- Lexical half of hybrid retrieval (rag-design.md section 1). PostgreSQL
  -- ships no Hindi Snowball stemmer, so Hindi rows use the 'simple'
  -- configuration (lowercase + stopwords, no stemming) and English rows use
  -- 'english' -- rag-design.md section 3. Generated, so it can never drift
  -- out of sync with `content`.
  tsv tsvector generated always as (
    case language
      when 'hi' then to_tsvector('simple'::regconfig, content)
      else to_tsvector('english'::regconfig, content)
    end
  ) stored,

  token_count integer,
  created_at timestamptz not null default now(),

  constraint chunks_document_chunk_index_key unique (document_id, chunk_index)
);

create index chunks_document_id_idx on public.chunks(document_id);
create index chunks_crop_id_idx on public.chunks(crop_id);
create index chunks_language_idx on public.chunks(language);

-- Dense retrieval. Cosine, because embeddings are L2-normalised at write
-- time, which makes cosine the matching metric.
create index chunks_embedding_hnsw_idx
  on public.chunks using hnsw (embedding extensions.vector_cosine_ops);

-- Lexical retrieval.
create index chunks_tsv_gin_idx on public.chunks using gin (tsv);

-- ------------------------------------------------------------------
-- RLS + grants
-- ------------------------------------------------------------------
alter table public.documents enable row level security;
alter table public.chunks enable row level security;

create policy "documents_select_all_authenticated"
  on public.documents for select
  to authenticated
  using (true);

create policy "chunks_select_all_authenticated"
  on public.chunks for select
  to authenticated
  using (true);

-- RLS policies decide which rows are visible; Postgres GRANTs decide whether
-- the role may touch the table at all -- both layers are required (the Phase 1
-- lesson, migration 20260830091500). Read-only: the app never writes corpus.
grant select on public.documents to authenticated;
grant select on public.chunks to authenticated;
