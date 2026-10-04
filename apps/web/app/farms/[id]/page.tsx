"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AskBox } from "@/components/AskBox";
import { buildDiary, Diary } from "@/components/Diary";
import { LogIrrigation } from "@/components/LogIrrigation";
import { ProfilePanel } from "@/components/ProfilePanel";
import { Shell } from "@/components/Shell";
import { ErrorNote } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import type { Activity, AdvisoryRecord, Crop, Farm, FarmCrop } from "@/lib/types";

export default function FarmHomePage() {
  const { t, lang } = useI18n();
  const { session, loading } = useAuth();
  const router = useRouter();
  const { id } = useParams<{ id: string }>();
  const token = session?.access_token;
  const [now] = useState(() => Date.now());

  const [farm, setFarm] = useState<Farm | null>(null);
  const [farmCrops, setFarmCrops] = useState<FarmCrop[]>([]);
  const [crops, setCrops] = useState<Crop[]>([]);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [advisories, setAdvisories] = useState<AdvisoryRecord[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !session) router.replace("/");
  }, [loading, session, router]);

  const fetchDiary = useCallback(
    (tok: string) =>
      Promise.all([api<Activity[]>(`/farms/${id}/timeline`, { token: tok }), api<AdvisoryRecord[]>(`/farms/${id}/advisories`, { token: tok })]),
    [id],
  );

  const reloadDiary = useCallback(async () => {
    if (!token) return;
    const [acts, advs] = await fetchDiary(token);
    setActivities(acts);
    setAdvisories(advs);
  }, [token, fetchDiary]);

  useEffect(() => {
    if (!token) return;
    Promise.all([
      api<Farm>(`/farms/${id}`, { token }),
      api<FarmCrop[]>(`/farms/${id}/crops`, { token }),
      api<Crop[]>("/crops", { token }),
      fetchDiary(token),
    ])
      .then(([f, fc, c, [acts, advs]]) => {
        setFarm(f);
        setFarmCrops(fc);
        setCrops(c);
        setActivities(acts);
        setAdvisories(advs);
      })
      .catch((e) => setError(e instanceof ApiError && e.status === 404 ? e.message : t("networkFailed")));
  }, [id, token, fetchDiary, t]);

  const active = farmCrops.find((fc) => fc.status === "active") ?? null;
  const activeCrop = active ? crops.find((c) => c.id === active.crop_id) : undefined;
  const diary = useMemo(() => buildDiary(activities, advisories), [activities, advisories]);
  const daysSince = active ? Math.max(0, Math.floor((now - new Date(active.sowing_date).getTime()) / 86_400_000)) : null;

  return (
    <Shell>
      <Link href="/" className="inline-block text-green-900 underline">
        {t("back")}
      </Link>
      {error && <ErrorNote>{error}</ErrorNote>}
      {!error && (!farm || !token) && <p>{t("loading")}</p>}
      {farm && token && (
        <>
          <div>
            <h1 className="text-2xl font-bold text-green-900">{farm.name}</h1>
            {activeCrop && daysSince !== null && (
              <p className="text-stone-700">
                {lang === "hi" ? activeCrop.name_hi : activeCrop.name_en} · {t("daysSinceSowing")} {daysSince} {t("daysUnit")}
              </p>
            )}
          </div>
          <ProfilePanel farm={farm} token={token} onSaved={setFarm} />
          <AskBox farmId={farm.id} token={token} onAnswered={() => void reloadDiary().catch(() => {})} />
          <LogIrrigation farmCropId={active?.id ?? null} token={token} onLogged={() => void reloadDiary().catch(() => {})} />
          <h2 className="pt-2 text-xl font-bold text-green-900">{t("farmDiary")}</h2>
          <Diary items={diary} />
        </>
      )}
    </Shell>
  );
}
