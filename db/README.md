# db/

SQL migrations for the AgriAI Supabase Postgres (project `agriai-db`). Checked in; applied forward. Never edit a migration's history — add a new migration.

- `migrations/` — ordered `.sql` files (schema, RLS policies, indexes, pgvector setup).

The proposed data model is in `docs/database/schema.md`. Enable the `vector` extension; put RLS on every user-owned table; HNSW on embeddings, GIN on `tsv`, btree on filter columns.
