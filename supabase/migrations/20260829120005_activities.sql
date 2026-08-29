create table public.activities (
  id uuid primary key default gen_random_uuid(),
  farm_crop_id uuid not null references public.farm_crops(id) on delete cascade,
  type text not null check (type in ('irrigation', 'fertiliser', 'spray', 'sowing', 'scouting', 'other')),
  occurred_on date not null,
  details jsonb not null default '{}'::jsonb,
  source text not null default 'farmer' check (source in ('farmer', 'agent-confirmed')),
  created_at timestamptz not null default now()
);

create index activities_farm_crop_id_idx on public.activities(farm_crop_id);

alter table public.activities enable row level security;

-- Ownership chain: activities -> farm_crops -> farms -> profile_id.
-- No update/delete policy: activities are an append-only timeline for now.
create policy "activities_select_own"
  on public.activities for select
  using (
    exists (
      select 1 from public.farm_crops
      join public.farms on farms.id = farm_crops.farm_id
      where farm_crops.id = activities.farm_crop_id
      and farms.profile_id = auth.uid()
    )
  );

create policy "activities_insert_own"
  on public.activities for insert
  with check (
    exists (
      select 1 from public.farm_crops
      join public.farms on farms.id = farm_crops.farm_id
      where farm_crops.id = activities.farm_crop_id
      and farms.profile_id = auth.uid()
    )
  );
