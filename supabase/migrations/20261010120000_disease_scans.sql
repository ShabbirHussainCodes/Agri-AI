-- Phase 7 (ADR-0018): crop-photo diagnosis. Two things:
--   1. public.disease_scans -- one row per photo check that cost a model call or ended in a verdict worth
--      keeping, with the DiagnosisResponse exactly as the farmer received it (jsonb: the contract grows and
--      history must not need a migration each time, as for advisories).
--   2. a PRIVATE storage bucket `crop-photos` whose row-level policy is the same ownership rule as the
--      farm data (ADR-0008): an object's first path segment is the farm id, and only the farm's owner can
--      read, write or delete it.
--
-- A photo is personal data (location, crop condition). No public bucket, no public URL: the app creates a
-- short-lived signed URL with the user's own session.

create table public.disease_scans (
  id uuid primary key default gen_random_uuid(),
  farm_id uuid not null references public.farms(id) on delete cascade,
  -- Key inside the crop-photos bucket: '<farm_id>/<scan id>.jpg'. Null when storing was not possible.
  image_path text,
  outcome text not null check (outcome in ('rejected_quality', 'abstained', 'diagnosis')),
  abstained_because text,
  response jsonb not null,
  -- {agrees: bool, confirmed_label: text|null}: the farmer's own correction, the seed of a field dataset.
  farmer_feedback jsonb,
  created_at timestamptz not null default now()
);

create index disease_scans_farm_created_idx on public.disease_scans (farm_id, created_at desc);
create index disease_scans_created_idx on public.disease_scans (created_at);

alter table public.disease_scans enable row level security;

create policy "disease_scans_select_own"
  on public.disease_scans for select
  using (exists (select 1 from public.farms where farms.id = disease_scans.farm_id and farms.profile_id = auth.uid()));

create policy "disease_scans_insert_own"
  on public.disease_scans for insert
  with check (exists (select 1 from public.farms where farms.id = disease_scans.farm_id and farms.profile_id = auth.uid()));

create policy "disease_scans_update_own"
  on public.disease_scans for update
  using (exists (select 1 from public.farms where farms.id = disease_scans.farm_id and farms.profile_id = auth.uid()))
  with check (exists (select 1 from public.farms where farms.id = disease_scans.farm_id and farms.profile_id = auth.uid()));

create policy "disease_scans_delete_own"
  on public.disease_scans for delete
  using (exists (select 1 from public.farms where farms.id = disease_scans.farm_id and farms.profile_id = auth.uid()));

-- Only the farmer's feedback may change after the fact: what the farmer was told is a record.
grant select, insert, delete on public.disease_scans to authenticated;
grant update (farmer_feedback) on public.disease_scans to authenticated;

-- ---------------------------------------------------------------------------------------------------
-- Daily caps. Photo checks and /ask draw on the same gpt-oss-120b free-tier budget, so the global figure
-- /ask is capped against now counts both; scans also have their own per-user and global counts.
create or replace function public.asks_in_last_day()
returns integer
language sql
stable
security definer
set search_path = public
as $$
  select (
    (select count(*) from public.advisories where created_at > now() - interval '24 hours')
    + (select count(*) from public.disease_scans
       where created_at > now() - interval '24 hours' and outcome <> 'rejected_quality')
  )::int
$$;

create function public.scans_in_last_day()
returns integer
language sql
stable
security definer
set search_path = public
as $$
  select count(*)::int from public.disease_scans
  where created_at > now() - interval '24 hours' and outcome <> 'rejected_quality'
$$;

revoke all on function public.scans_in_last_day() from public;
grant execute on function public.scans_in_last_day() to authenticated;

-- ---------------------------------------------------------------------------------------------------
-- Private bucket. NOTE for the policies below: inside the EXISTS subquery an unqualified `name` would bind to
-- public.farms.name (the farm's name), not storage.objects.name, so the column is written objects.name.
-- (Found by tests/test_storage_supabase.py: with `name` the owner's own upload was denied.)
-- The classifier and the model only ever see the re-encoded, EXIF-free JPEG that the API
-- stores, never the original upload, so the bucket accepts only image/jpeg and a small size.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('crop-photos', 'crop-photos', false, 2097152, array['image/jpeg'])
on conflict (id) do nothing;

create policy "crop_photos_select_own"
  on storage.objects for select to authenticated
  using (
    bucket_id = 'crop-photos'
    and exists (
      select 1 from public.farms
      where farms.id::text = (storage.foldername(objects.name))[1] and farms.profile_id = auth.uid()
    )
  );

create policy "crop_photos_insert_own"
  on storage.objects for insert to authenticated
  with check (
    bucket_id = 'crop-photos'
    and exists (
      select 1 from public.farms
      where farms.id::text = (storage.foldername(objects.name))[1] and farms.profile_id = auth.uid()
    )
  );

create policy "crop_photos_delete_own"
  on storage.objects for delete to authenticated
  using (
    bucket_id = 'crop-photos'
    and exists (
      select 1 from public.farms
      where farms.id::text = (storage.foldername(objects.name))[1] and farms.profile_id = auth.uid()
    )
  );
