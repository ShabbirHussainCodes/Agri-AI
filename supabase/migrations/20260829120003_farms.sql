create table public.farms (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles(id) on delete cascade,
  name text not null,
  lat double precision,
  lon double precision,
  district text,
  state text,
  agro_climatic_zone text,
  area_ha numeric,
  soil_ph numeric,
  soil_n numeric,
  soil_p numeric,
  soil_k numeric,
  created_at timestamptz not null default now()
);

create index farms_profile_id_idx on public.farms(profile_id);

alter table public.farms enable row level security;

create policy "farms_select_own"
  on public.farms for select
  using (auth.uid() = profile_id);

create policy "farms_insert_own"
  on public.farms for insert
  with check (auth.uid() = profile_id);

create policy "farms_update_own"
  on public.farms for update
  using (auth.uid() = profile_id)
  with check (auth.uid() = profile_id);
