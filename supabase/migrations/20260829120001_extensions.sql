-- Extensions AgriAI needs.
-- vector: pgvector, for RAG embeddings later (Phase 3+). Enabled now so
-- future migrations don't need a separate extension step.
create extension if not exists vector;

-- pgcrypto: gen_random_uuid() for primary keys.
create extension if not exists pgcrypto;
