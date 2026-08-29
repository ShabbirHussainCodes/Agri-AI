-- Reference table (not farmer-owned): every authenticated user may read it;
-- only service_role (ingestion/admin) may write it, since no write policy
-- exists below for the 'authenticated' role.
create table public.crops (
  id uuid primary key default gen_random_uuid(),
  name_en text not null,
  name_hi text not null,
  default_duration_days integer,
  created_at timestamptz not null default now()
);

alter table public.crops enable row level security;

create policy "crops_select_all_authenticated"
  on public.crops for select
  to authenticated
  using (true);

-- A specific planting on a specific farm.
create table public.farm_crops (
  id uuid primary key default gen_random_uuid(),
  farm_id uuid not null references public.farms(id) on delete cascade,
  crop_id uuid not null references public.crops(id),
  variety text,
  sowing_date date not null,
  expected_harvest date,
  status text not null default 'active' check (status in ('active', 'harvested')),
  created_at timestamptz not null default now()
);

create index farm_crops_farm_id_idx on public.farm_crops(farm_id);

alter table public.farm_crops enable row level security;

-- farm_crops has no profile_id column of its own, so ownership is checked
-- by joining up to farms. This EXISTS-subquery-join pattern is how RLS
-- handles "ownership through a parent row" — you'll see it again below.
create policy "farm_crops_select_own"
  on public.farm_crops for select
  using (
    exists (
      select 1 from public.farms
      where farms.id = farm_crops.farm_id
      and farms.profile_id = auth.uid()
    )
  );

create policy "farm_crops_insert_own"
  on public.farm_crops for insert
  with check (
    exists (
      select 1 from public.farms
      where farms.id = farm_crops.farm_id
      and farms.profile_id = auth.uid()
    )
  );

create policy "farm_crops_update_own"
  on public.farm_crops for update
  using (
    exists (
      select 1 from public.farms
      where farms.id = farm_crops.farm_id
      and farms.profile_id = auth.uid()
    )
  )
  with check (
    exists (
      select 1 from public.farms
      where farms.id = farm_crops.farm_id
      and farms.profile_id = auth.uid()
    )
  );

-- Reference data lives in the migration (not supabase/seed.sql) on purpose:
-- seed.sql only runs for local `supabase db reset`, but this migration will
-- also run against the real agriai-db project later, so production gets
-- these rows automatically too.
insert into public.crops (name_en, name_hi, default_duration_days) values
  ('Wheat', 'गेहूं', 130),
  ('Rice (Paddy)', 'धान', 120),
  ('Cotton', 'कपास', 180),
  ('Sugarcane', 'गन्ना', 365),
  ('Maize', 'मक्का', 100),
  ('Soybean', 'सोयाबीन', 100),
  ('Mustard', 'सरसों', 120),
  ('Chickpea (Gram)', 'चना', 100),
  ('Potato', 'आलू', 90),
  ('Tomato', 'टमाटर', 90);
