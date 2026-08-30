-- The "Automatically expose new tables" setting was intentionally disabled
-- when this project was created (see Checkpoint 7 discussion) -- Supabase's
-- own recommendation, for precise/manual access control. Local Supabase's
-- dev bootstrap grants broad default privileges to `authenticated`/`anon`
-- regardless of that setting, which is why this only surfaced when testing
-- against the real remote project: RLS *policies* decide which rows are
-- visible, but Postgres's own GRANT system decides whether the role can
-- touch the table at all -- both layers are required, and only the second
-- was missing here. Granting exactly what each table's RLS policies need
-- (least privilege), not a blanket ALL.

grant select, insert, update on public.profiles to authenticated;
grant select, insert, update on public.farms to authenticated;
grant select on public.crops to authenticated;
grant select, insert, update on public.farm_crops to authenticated;
grant select, insert on public.activities to authenticated;
