"use client";

import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { askBody } from "@/lib/askBody";
import { SEND_UI_LANGUAGE } from "@/lib/config";
import { useI18n } from "@/lib/i18n";
import { pickLanguage } from "@/lib/text";
import type { AdvisoryResponse } from "@/lib/types";
import { AnswerCard } from "./AnswerCard";
import { Button, Card, ErrorNote, inputClass } from "./ui";

/** The one place a farmer asks. Every answer is rendered by AnswerCard, which keeps the evidence
 *  types apart; a daily-limit answer (429) carries its own bilingual message from the API. */
export function AskBox({ farmId, token, onAnswered }: { farmId: string; token: string; onAnswered: () => void }) {
  const { t, lang } = useI18n();
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [answer, setAnswer] = useState<AdvisoryResponse | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q || busy) return;
    setBusy(true);
    setError(null);
    setAnswer(null);
    try {
      const r = await api<AdvisoryResponse>(`/farms/${farmId}/ask`, { method: "POST", body: askBody(q, lang, SEND_UI_LANGUAGE), token });
      setAnswer(r);
      setQuestion("");
      onAnswered();
    } catch (err) {
      if (err instanceof ApiError && err.code === "ask_limit_reached") setError(pickLanguage(err.message, lang));
      else if (err instanceof ApiError && err.status === 0) setError(t("networkFailed"));
      else setError(t("askFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="space-y-3">
      <form onSubmit={submit} className="space-y-3">
        <label className="block space-y-1">
          <span className="text-lg font-bold text-green-900">{t("ask")}</span>
          <textarea
            className={`${inputClass} min-h-24`}
            maxLength={1000}
            placeholder={t("askPlaceholder")}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
        </label>
        <Button type="submit" className="w-full" disabled={busy || question.trim() === ""}>
          {busy ? t("thinking") : t("askButton")}
        </Button>
      </form>
      {error && <ErrorNote>{error}</ErrorNote>}
      {answer && <AnswerCard r={answer} />}
    </Card>
  );
}
