"use client";

import { useState } from "react";
import { useI18n } from "@/lib/i18n";
import { Button, Field, inputClass } from "./ui";

export type Coords = { lat: string; lon: string };

/** Location by one tap (the phone's GPS) or typed by hand. Kept as strings while editing so a
 *  half-typed number is not rewritten under the farmer's finger; the caller validates. */
export function LocationField({ value, onChange }: { value: Coords; onChange: (v: Coords) => void }) {
  const { t } = useI18n();
  const [denied, setDenied] = useState(false);

  function useGps() {
    setDenied(false);
    if (!navigator.geolocation) return setDenied(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => onChange({ lat: pos.coords.latitude.toFixed(5), lon: pos.coords.longitude.toFixed(5) }),
      () => setDenied(true),
      { enableHighAccuracy: false, timeout: 10000 },
    );
  }

  return (
    <fieldset className="space-y-2">
      <legend className="text-base font-semibold text-stone-800">{t("location")}</legend>
      <p className="text-sm text-stone-700">{t("locationWhy")}</p>
      <Button type="button" variant="secondary" onClick={useGps} className="w-full">
        {t("useMyLocation")}
      </Button>
      {denied && <p className="text-sm text-amber-900">{t("locationDenied")}</p>}
      <div className="grid grid-cols-2 gap-2">
        <Field label={t("lat")}>
          <input className={inputClass} inputMode="decimal" value={value.lat} onChange={(e) => onChange({ ...value, lat: e.target.value })} />
        </Field>
        <Field label={t("lon")}>
          <input className={inputClass} inputMode="decimal" value={value.lon} onChange={(e) => onChange({ ...value, lon: e.target.value })} />
        </Field>
      </div>
    </fieldset>
  );
}

/** "" -> both empty (no location); otherwise both must be numbers in range, else null (= invalid). */
export function parseCoords(c: Coords): { lat: number; lon: number } | "none" | null {
  if (c.lat.trim() === "" && c.lon.trim() === "") return "none";
  const lat = Number(c.lat);
  const lon = Number(c.lon);
  if (c.lat.trim() === "" || c.lon.trim() === "" || !Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null;
  return { lat, lon };
}
