"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { MessageKey } from "@/lib/messages";
import { pickLanguage } from "@/lib/text";
import type { DiagnosisResponse, ScanCandidate } from "@/lib/types";
import { AnswerCard } from "./AnswerCard";
import { Button, Card } from "./ui";

const BAND: Record<"high" | "medium" | "low", { key: MessageKey; style: string }> = {
  high: { key: "bandHigh", style: "bg-green-100 text-green-950 ring-green-500" },
  medium: { key: "bandMedium", style: "bg-amber-100 text-amber-950 ring-amber-500" },
  low: { key: "bandLow", style: "bg-stone-100 text-stone-900 ring-stone-400" },
};

/**
 * One photo check, rendered so that what the models SAW, what the LABEL says and the RECOMMENDATION stay
 * apart (docs/ai/multimodal-vision.md section 3):
 *   - top-3, never a bare top-1: the agreed estimate first, the others labelled "it could also be";
 *   - no percentage as "confidence": only a band (high/medium/low) and what that band scored in our tests;
 *   - refusals are calm: "AgriAI is not naming a disease", with what to do next, in code's own words;
 *   - the advice, label card and documents are the same AnswerCard as for a question.
 * A rejected photo is a different, plainer card: take it again.
 */
export function ScanCard({
  r,
  photoUrl,
  token,
  feedback,
  onDeleted,
}: {
  r: DiagnosisResponse;
  photoUrl?: string | null;
  token?: string;
  feedback?: { agrees: boolean } | null;
  onDeleted?: () => void;
}) {
  const { t, lang } = useI18n();

  if (r.outcome === "rejected_quality") {
    return (
      <div data-testid="scan-result">
        <Card className="bg-amber-50 ring-amber-300">
          <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-amber-900">{t("scanRetakeTitle")}</h2>
          <p className="whitespace-pre-line text-lg text-stone-900">{pickLanguage(r.message, lang)}</p>
        </Card>
      </div>
    );
  }

  if (r.outcome === "abstained") {
    return (
      <div className="space-y-3" data-testid="scan-result">
        <Card className="bg-sky-50 ring-sky-300">
          <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-stone-600">{t("scanNoNameTitle")}</h2>
          {photoUrl && <Photo url={photoUrl} />}
          <p className="whitespace-pre-line text-lg leading-relaxed text-stone-900">{pickLanguage(r.message, lang)}</p>
        </Card>
        <Actions r={r} token={token} feedback={null} onDeleted={onDeleted} />
      </div>
    );
  }

  const leading = r.candidates.find((c) => c.leading) ?? r.candidates[0];
  const others = r.candidates.filter((c) => c !== leading);
  const band = r.band ? BAND[r.band.name] : null;
  return (
    <div className="space-y-3" data-testid="scan-result">
      <Card className="ring-green-300">
        <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-stone-600">{t("scanLikelyTitle")}</h2>
        {photoUrl && <Photo url={photoUrl} />}
        {leading && (
          <>
            <p className="text-2xl font-bold text-green-950">{name(leading, lang)}</p>
            <p className="text-sm text-stone-600">{name(leading, lang === "hi" ? "en" : "hi")}</p>
            {leading.second_opinion_agrees && <p className="mt-2 font-semibold text-green-900">✓ {t("scanSecondCheck")}</p>}
          </>
        )}
        {r.band && band && (
          <div className="mt-3">
            <p className="text-base text-stone-800">
              {t("scanConfidence")}:{" "}
              <span className={`inline-block rounded-full px-3 py-0.5 font-bold ring-2 ${band.style}`}>{t(band.key)}</span>
            </p>
            {r.band.n > 0 && (
              <p className="mt-1 text-sm text-stone-700">
                {t("bandMeasured")
                  .replace("{pct}", String(Math.round(r.band.observed_accuracy * 100)))
                  .replace("{n}", String(r.band.n))
                  .replace("{source}", r.band.measured_on.split(":")[0])}
              </p>
            )}
          </div>
        )}
        {others.length > 0 && (
          <p className="mt-3 text-base text-stone-800">
            {t("scanOthers")}: {others.map((c) => name(c, lang)).join(" · ")}
          </p>
        )}
      </Card>

      {r.model_saw && (r.model_saw.symptoms || r.model_saw.plant_part) && (
        <Card className="bg-stone-50">
          <h2 className="mb-1 text-sm font-bold uppercase tracking-wide text-stone-600">👁️ {t("scanSawTitle")}</h2>
          {r.model_saw.symptoms && <p className="text-base text-stone-800">{r.model_saw.symptoms}</p>}
        </Card>
      )}

      {r.advisory && <AnswerCard r={r.advisory} />}

      {r.note && <p className="rounded-xl bg-amber-50 p-3 text-base font-semibold text-amber-950">{pickLanguage(r.note, lang)}</p>}
      <Actions r={r} token={token} feedback={feedback ?? null} onDeleted={onDeleted} />
    </div>
  );
}

function name(c: ScanCandidate, lang: "hi" | "en"): string {
  return lang === "hi" ? c.name_hi : c.name_en;
}

function Photo({ url }: { url: string }) {
  const { t } = useI18n();
  // eslint-disable-next-line @next/next/no-img-element -- a signed, short-lived storage URL or a local blob: next/image cannot optimise either
  return <img src={url} alt={t("photoAlt")} className="mb-3 max-h-60 w-full rounded-xl object-cover" />;
}

/** The farmer's own verdict on the estimate, and the way to remove the check and its photo. Both need a saved
 *  scan (an id) and a session; neither exists for a refused photo that was never saved. */
function Actions({
  r,
  token,
  feedback,
  onDeleted,
}: {
  r: DiagnosisResponse;
  token?: string;
  feedback: { agrees: boolean } | null;
  onDeleted?: () => void;
}) {
  const { t } = useI18n();
  const [sent, setSent] = useState<boolean>(feedback !== null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  if (!r.scan_id || !token) return null;

  async function send(agrees: boolean) {
    setBusy(true);
    try {
      await api(`/scans/${r.scan_id}/feedback`, { method: "POST", token: token!, body: { agrees } });
      setSent(true);
    } catch {
      /* feedback is a courtesy: a failure must not disturb the answer */
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await api(`/scans/${r.scan_id}`, { method: "DELETE", token: token! });
      onDeleted?.();
    } catch {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      {r.outcome === "diagnosis" &&
        (sent ? (
          <p role="status" className="px-1 text-stone-700">{t("scanFeedbackThanks")}</p>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold text-stone-800">{t("scanFeedbackAsk")}</span>
            <Button variant="secondary" disabled={busy} onClick={() => void send(true)}>{t("scanFeedbackYes")}</Button>
            <Button variant="secondary" disabled={busy} onClick={() => void send(false)}>{t("scanFeedbackNo")}</Button>
          </div>
        ))}
      {confirm ? (
        <div className="flex items-center gap-2">
          <span className="font-semibold">{t("scanDeleteSure")}</span>
          <Button disabled={busy} onClick={() => void remove()}>{t("record")}</Button>
          <Button variant="quiet" onClick={() => setConfirm(false)}>{t("cancel")}</Button>
        </div>
      ) : (
        <Button variant="quiet" onClick={() => setConfirm(true)}>{t("scanDelete")}</Button>
      )}
    </div>
  );
}
