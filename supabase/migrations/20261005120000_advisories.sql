-- ADR-0017: every answer is kept, so the farm timeline can show past questions
-- (the product's persistent-state differentiation) and so /ask can enforce a
-- daily cap on a free-tier LLM budget.
--
-- Ownership goes through the farm, like activities: a row is visible and
-- insertable only for a farm the caller owns. No update or delete: an advisory
-- is a record of what the farmer was told.

create table public.advisories (
  id uuid primary key default gen_random_uuid(),
  farm_id uuid not null references public.farms(id) on delete cascade,
  question text not null,
  -- The AdvisoryResponse exactly as the farmer received it. jsonb, not columns:
  -- the contract grows (water_balance, agrochemical_label ...) and history must
  -- not need a migration each time.
  response jsonb not null,
  abstained boolean not null,
  created_at timestamptz not null default now()
);

create index advisories_farm_created_idx on public.advisories (farm_id, created_at desc);
create index advisories_created_idx on public.advisories (created_at);

alter table public.advisories enable row level security;

create policy "advisories_select_own"
  on public.advisories for select
  using (
    exists (
      select 1 from public.farms
      where farms.id = advisories.farm_id and farms.profile_id = auth.uid()
    )
  );

create policy "advisories_insert_own"
  on public.advisories for insert
  with check (
    exists (
      select 1 from public.farms
      where farms.id = advisories.farm_id and farms.profile_id = auth.uid()
    )
  );

grant select, insert on public.advisories to authenticated;

-- A COUNT across all farmers, for the global daily cap. RLS would hide other
-- people's rows from a plain count, so this runs as the owner. It returns one
-- number and exposes no row.
create function public.asks_in_last_day()
returns integer
language sql
stable
security definer
set search_path = public
as $$
  select count(*)::int from public.advisories where created_at > now() - interval '24 hours'
$$;

revoke all on function public.asks_in_last_day() from public;
grant execute on function public.asks_in_last_day() to authenticated;
