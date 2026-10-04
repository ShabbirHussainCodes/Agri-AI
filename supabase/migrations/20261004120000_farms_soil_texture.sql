-- ADR-0015: soil type, in the farmer's own words, for the irrigation water balance.
--
-- Three classes on purpose. A farmer knows retili (sandy), domat (loamy) and
-- chikni/kali (clayey) soil without a lab report; each maps to one reviewed
-- row of the crop/soil reference table (data/crop_water/). Nullable: an
-- existing farm has no answer yet, and the app then says "tell us your soil
-- type" instead of guessing a default (a wrong soil roughly doubles the
-- error in the available-water estimate).
--
-- Existing RLS policies on public.farms (select/insert/update own) already
-- cover the new column; nothing to add.

alter table public.farms
  add column soil_texture text
    check (soil_texture in ('sandy', 'loamy', 'clayey'));

comment on column public.farms.soil_texture is
  'ADR-0015: sandy (retili) | loamy (domat) | clayey (chikni/kali). Null = not told yet.';
