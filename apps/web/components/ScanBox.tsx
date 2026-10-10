"use client";

import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { SEND_UI_LANGUAGE } from "@/lib/config";
import { resizeForUpload } from "@/lib/image";
import { useI18n } from "@/lib/i18n";
import { pickLanguage } from "@/lib/text";
import type { DiagnosisResponse } from "@/lib/types";
import { ScanCard } from "./ScanCard";
import { Button, Card, ErrorNote } from "./ui";

/** Take or choose one photo of a leaf and have it checked (Phase 7, ADR-0018). The camera button opens the
 *  phone's camera directly; the gallery button is for a photo taken earlier. The photo is shrunk on the phone
 *  first. Everything the farmer reads about the result is written by the API (a refusal in code's own words). */
export function ScanBox({ farmId, token, onScanned }: { farmId: string; token: string; onScanned: () => void }) {
  const { t, lang } = useI18n();
  const camera = useRef<HTMLInputElement>(null);
  const gallery = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DiagnosisResponse | null>(null);

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  function pick(f: File | undefined) {
    if (!f) return;
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setResult(null);
    setError(null);
  }

  async function check() {
    if (!file || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const form = new FormData();
      form.append("image", await resizeForUpload(file), "photo.jpg");
      if (SEND_UI_LANGUAGE) form.append("language", lang);
      const r = await api<DiagnosisResponse>(`/farms/${farmId}/scans`, { method: "POST", form, token });
      setResult(r);
      if (r.scan_id) onScanned();
    } catch (err) {
      if (err instanceof ApiError && err.status === 0) setError(t("networkFailed"));
      // The API's own 4xx messages (photo too large, daily limit ...) are bilingual and written for the farmer.
      else if (err instanceof ApiError && err.status >= 400 && err.status < 500 && err.code) setError(pickLanguage(err.message, lang));
      else setError(t("scanFailed"));
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setFile(null);
    setPreview(null);
    setResult(null);
    setError(null);
  }

  return (
    <Card className="space-y-3">
      <h2 className="text-lg font-bold text-green-900">{t("scanTitle")}</h2>
      <p className="text-base text-stone-700">{t("scanHelp")}</p>
      <input ref={camera} data-testid="scan-camera" type="file" accept="image/*" capture="environment" className="sr-only" tabIndex={-1} onChange={(e) => pick(e.target.files?.[0])} />
      <input ref={gallery} data-testid="scan-gallery" type="file" accept="image/*" className="sr-only" tabIndex={-1} onChange={(e) => pick(e.target.files?.[0])} />
      <div className="grid grid-cols-2 gap-2">
        <Button variant="secondary" disabled={busy} onClick={() => camera.current?.click()}>{t("takePhoto")}</Button>
        <Button variant="secondary" disabled={busy} onClick={() => gallery.current?.click()}>{t("choosePhoto")}</Button>
      </div>
      {preview && !result && (
        // eslint-disable-next-line @next/next/no-img-element -- a local blob URL
        <img src={preview} alt={t("photoAlt")} className="max-h-60 w-full rounded-xl object-cover" />
      )}
      {file && !result && (
        <Button className="w-full" disabled={busy} onClick={() => void check()}>
          {busy ? t("checking") : t("checkPhoto")}
        </Button>
      )}
      {error && <ErrorNote>{error}</ErrorNote>}
      {result && (
        <>
          <ScanCard r={result} photoUrl={preview} token={token} onDeleted={() => { reset(); onScanned(); }} />
          <Button variant="secondary" className="w-full" onClick={reset}>{t("anotherPhoto")}</Button>
        </>
      )}
    </Card>
  );
}
