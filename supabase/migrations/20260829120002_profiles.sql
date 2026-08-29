-- The farmer. id = auth.users(id) (Supabase Auth's own user id), so
-- auth.uid() in every RLS policy below always resolves to a real farmer.
create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  preferred_language text not null default 'hi' check (preferred_language in ('hi', 'en')),
  phone text,
  created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

-- A farmer can see and change only their own profile row. No delete policy
-- (deliberate): profile deletion is out of scope for now — default-deny.
create policy "profiles_select_own"
  on public.profiles for select
  using (auth.uid() = id);

create policy "profiles_insert_own"
  on public.profiles for insert
  with check (auth.uid() = id);

create policy "profiles_update_own"
  on public.profiles for update
  using (auth.uid() = id)
  with check (auth.uid() = id);
