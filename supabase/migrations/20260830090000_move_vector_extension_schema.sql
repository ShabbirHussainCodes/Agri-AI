-- Fixes Supabase linter WARN "extension_in_public": pgvector was installed
-- into the public schema by the earlier `extensions` migration. Moving it
-- now, before any table depends on the vector type, is free; doing it
-- later (Phase 3, once embeddings columns exist) would not be.
create schema if not exists extensions;
alter extension vector set schema extensions;
