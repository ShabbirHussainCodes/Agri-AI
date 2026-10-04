"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { LocationField, parseCoords, type Coords } from "@/components/LocationField";
import { Shell } from "@/components/Shell";
import { SoilPicker } from "@/components/SoilPicker";
import { Button, Card, ErrorNote, Field, inputClass } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { todayLocal } from "@/lib/dates";
import { useI18n } from "@/lib/i18n";
import type { Crop, Farm, FarmCreate, SoilTexture } from "@/lib/types";

export default function NewFarmPage() {
  const { t, lang } = useI18n();
  const { session, loading } = useAuth();
  const router = useRouter();
  const token = session?.access_token;

  const [crops, setCrops] = useState<Crop[]>([]);
  const [name, setName] = useState("");
  const [coords, setCoords] = useState<Coords>({ lat: "", lon: "" });
  const [soil, setSoil] = useState<SoilTexture | null>(null);
  const [cropId, setCropId] = useState("");
  const [sowing, setSowing] = useState(todayLocal());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !session) router.replace("/");
  }, [loading, session, router]);

  useEffect(() => {
    if (!token) return;
    api<Crop[]>("/crops", { token }).then(setCrops).catch(() => setError(t("networkFailed")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    const parsed = parseCoords(coords);
    if (parsed === null) return setError(t("locationDenied"));
    setBusy(true);
    setError(null);
    try {
      const body: FarmCreate = {
        name: name.trim(),
        ...(parsed !== "none" ? { lat: parsed.lat, lon: parsed.lon } : {}),
        ...(soil ? { soil_texture: soil } : {}),
      };
      const farm = await api<Farm>("/farms", { method: "POST", body, token });
      if (cropId) {
        await api(`/farms/${farm.id}/crops`, { method: "POST", body: { crop_id: cropId, sowing_date: sowing }, token });
      }
      router.replace(`/farms/${farm.id}`);
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 0 ? err.message : t("networkFailed"));
      setBusy(false);
    }
  }

  return (
    <Shell>
      <h1 className="text-2xl font-bold text-green-900">{t("newFarm")}</h1>
      <form onSubmit={submit} className="space-y-5">
        <Card className="space-y-4">
          <Field label={t("farmName")}>
            <input className={inputClass} required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <LocationField value={coords} onChange={setCoords} />
          <SoilPicker value={soil} onChange={setSoil} />
        </Card>
        <Card className="space-y-4">
          <Field label={t("crop")}>
            <select className={inputClass} value={cropId} onChange={(e) => setCropId(e.target.value)}>
              <option value="">{t("chooseCrop")}</option>
              {crops.map((c) => (
                <option key={c.id} value={c.id}>
                  {lang === "hi" ? c.name_hi : c.name_en}
                </option>
              ))}
            </select>
          </Field>
          {cropId && (
            <Field label={t("sowingDate")}>
              <input type="date" className={inputClass} required max={todayLocal()} value={sowing} onChange={(e) => setSowing(e.target.value)} />
            </Field>
          )}
        </Card>
        {error && <ErrorNote>{error}</ErrorNote>}
        <Button type="submit" className="w-full" disabled={busy || name.trim() === ""}>
          {busy ? t("saving") : t("saveFarm")}
        </Button>
      </form>
    </Shell>
  );
}
