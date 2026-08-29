# db/

**Moved 2026-08-29:** migrations now live in `supabase/migrations/`, managed by the Supabase CLI (see ADR-0011 and CLAUDE.md §7). This folder is kept only so old links don't 404; it holds no active files.

Why: RLS testing needs Supabase's own `auth.uid()`/`auth.users`/role machinery, which a plain Postgres container doesn't have — the Supabase CLI's local stack (`supabase start`) provisions all of it, matching the real `agriai-db` project.
