"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { todayLocal } from "@/lib/dates";
import { useI18n } from "@/lib/i18n";
import { Button, Card, ErrorNote, Field, inputClass } from "./ui";

/** "I irrigated today" in two taps. The farm record changes only after the farmer confirms
 *  (CLAUDE.md rule 8): the button opens a confirmation, it never writes by itself. */
export function LogIrrigation({ farmCropId, token, onLogged }: { farmCropId: string | null; token: string; onLogged: () => void }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [depth, setDepth] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  if (!farmCropId) return <p className="text-stone-700">{t("noActiveCrop")}</p>;

  async function record() {
    const mm = depth.trim() === "" ? null : Number(depth);
    if (mm !== null && (!Number.isFinite(mm) || mm <= 0 || mm > 500)) return setError(t("depthLabel"));
    setBusy(true);
    setError(null);
    try {
      await api(`/farm-crops/${farmCropId}/activities`, {
        method: "POST",
        token,
        body: { type: "irrigation", occurred_on: todayLocal(), details: mm === null ? {} : { depth_mm: mm } },
      });
      setDone(true);
      setOpen(false);
      setDepth("");
      onLogged();
    } catch (err) {
      setError(err instanceof ApiError && err.status === 0 ? t("networkFailed") : t("askFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <Button variant="secondary" className="w-full" onClick={() => { setOpen(true); setDone(false); }}>
        {t("logIrrigation")}
      </Button>
      {done && <p role="status" className="rounded-xl bg-green-50 p-3 text-green-900">{t("recorded")}</p>}
      {open && (
        <Card className="space-y-3 ring-2 ring-green-700">
          <p className="text-lg font-bold">{t("logIrrigationTitle")}</p>
          <p className="text-stone-700">{t("logIrrigationWhy")}</p>
          <Field label={t("depthLabel")}>
            <input className={inputClass} inputMode="decimal" value={depth} onChange={(e) => setDepth(e.target.value)} />
          </Field>
          {error && <ErrorNote>{error}</ErrorNote>}
          <div className="flex gap-2">
            <Button onClick={record} disabled={busy} className="flex-1">{t("record")}</Button>
            <Button variant="quiet" onClick={() => setOpen(false)}>{t("cancel")}</Button>
          </div>
        </Card>
      )}
    </div>
  );
}
