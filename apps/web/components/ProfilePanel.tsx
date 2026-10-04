"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Farm, FarmUpdate, SoilTexture } from "@/lib/types";
import { LocationField, parseCoords, type Coords } from "./LocationField";
import { SoilPicker } from "./SoilPicker";
import { Button, Card, ErrorNote } from "./ui";

/** Soil and location are what unlock the irrigation calculation (ADR-0015); farms made before
 *  they existed have neither, so the farm home asks for them here. */
export function ProfilePanel({ farm, token, onSaved }: { farm: Farm; token: string; onSaved: (f: Farm) => void }) {
  const { t } = useI18n();
  const incomplete = !farm.soil_texture || farm.lat == null || farm.lon == null;
  const [open, setOpen] = useState(false);
  const [soil, setSoil] = useState<SoilTexture | null>(farm.soil_texture ?? null);
  const [coords, setCoords] = useState<Coords>({ lat: farm.lat?.toString() ?? "", lon: farm.lon?.toString() ?? "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    const parsed = parseCoords(coords);
    if (parsed === null) return setError(t("locationDenied"));
    const body: FarmUpdate = {
      ...(soil ? { soil_texture: soil } : {}),
      ...(parsed !== "none" ? { lat: parsed.lat, lon: parsed.lon } : {}),
    };
    setBusy(true);
    setError(null);
    try {
      onSaved(await api<Farm>(`/farms/${farm.id}`, { method: "PATCH", body, token }));
      setOpen(false);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 0 ? t("networkFailed") : t("askFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      {incomplete && !open && (
        <p role="note" className="rounded-xl bg-amber-50 p-3 text-amber-950 ring-1 ring-amber-300">
          {t("profileIncomplete")}
        </p>
      )}
      {!open ? (
        <Button variant={incomplete ? "secondary" : "quiet"} onClick={() => setOpen(true)}>
          {t("editFarm")}
        </Button>
      ) : (
        <Card className="space-y-4">
          <SoilPicker value={soil} onChange={setSoil} />
          <LocationField value={coords} onChange={setCoords} />
          {error && <ErrorNote>{error}</ErrorNote>}
          <div className="flex gap-2">
            <Button onClick={save} disabled={busy} className="flex-1">{busy ? t("saving") : t("save")}</Button>
            <Button variant="quiet" onClick={() => setOpen(false)}>{t("cancel")}</Button>
          </div>
        </Card>
      )}
    </div>
  );
}
