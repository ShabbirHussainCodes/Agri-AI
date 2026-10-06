"use client";

import { useI18n } from "@/lib/i18n";
import type { MessageKey } from "@/lib/messages";
import { useCropName } from "@/lib/crops";
import { pickLanguage } from "@/lib/text";
import type { AdvisoryResponse, EvidenceItem, LabelEntry, WaterBalance } from "@/lib/types";
import { Card } from "./ui";

/**
 * One answer, with each kind of evidence visibly different (CLAUDE.md rule 3,
 * frontend-architecture.md):
 *   - the advice itself, first and large;
 *   - "calculated by AgriAI" (code computed it: water balance);
 *   - the pesticide label card (copied by code from a verified table, never written by the model);
 *   - "what the documents say" (quotes, with source), marked as not verified advice;
 *   - "how the AI reasoned" (the model's own inference), collapsed.
 * Abstention is a calm, normal state, not an error.
 */
export function AnswerCard({ r }: { r: AdvisoryResponse }) {
  const { t, lang } = useI18n();
  const wb = r.water_balance && r.water_balance.verdict !== "cannot_assess" ? r.water_balance : null;
  const hasLabel = r.agrochemical_label.length > 0;
  const farm = r.structured_data;
  const cropName = useCropName(farm.crop_name);

  return (
    <div className="space-y-3" data-testid="answer">
      <Card className={r.abstained ? "bg-sky-50 ring-sky-300" : "ring-green-300"}>
        <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-stone-600">
          {r.abstained ? t("noReliableAnswer") : t("adviceTitle")}
        </h2>
        <p className="whitespace-pre-line text-lg leading-relaxed text-stone-900">{pickLanguage(r.recommendation, lang)}</p>
        {hasLabel && !r.abstained && <p className="mt-2 text-base font-semibold text-green-900">{t("seeLabelCard")}</p>}
        {cropName && (
          <p className="mt-3 text-sm text-stone-600">
            {cropName}
            {farm.days_since_sowing != null && ` · ${t("daysSinceSowing")} ${farm.days_since_sowing} ${t("daysUnit")}`}
          </p>
        )}
      </Card>

      {/* Code-written note about what the answer does not rest on. Answers saved before the field existed
          have no `limitations` at all, so this tests the value, not the type. */}
      {r.limitations && !r.abstained && (
        <Card className="bg-stone-50">
          <h2 className="mb-1 text-sm font-bold uppercase tracking-wide text-stone-600">ℹ️ {t("limitationsTitle")}</h2>
          <p className="whitespace-pre-line text-base text-stone-800">{pickLanguage(r.limitations, lang)}</p>
        </Card>
      )}

      {wb && <WaterBalanceCard wb={wb} />}
      {hasLabel && !r.abstained && r.agrochemical_label.map((e) => <LabelCard key={e.row_id} entry={e} />)}
      {r.retrieved_evidence.length > 0 && !r.abstained && <Sources items={r.retrieved_evidence} />}

      {r.live_data && !r.abstained && (
        <p className="px-1 text-sm text-stone-600">
          {t("weatherTitle")}: {r.live_data.current_temp_c != null && `${r.live_data.current_temp_c}°C`}
          {r.live_data.current_rain_mm != null && ` · ${r.live_data.current_rain_mm} mm`}
        </p>
      )}

      {r.model_inference && !r.abstained && (
        <details className="rounded-2xl bg-white p-4 ring-1 ring-stone-200">
          <summary className="cursor-pointer text-base font-semibold text-stone-700">{t("reasoningTitle")}</summary>
          <p className="mt-2 whitespace-pre-line text-base text-stone-700">{r.model_inference}</p>
        </details>
      )}
    </div>
  );
}

const VERDICT: Record<"irrigate_now" | "wait", { key: MessageKey; style: string }> = {
  irrigate_now: { key: "verdictIrrigateNow", style: "bg-amber-100 text-amber-950 ring-amber-400" },
  wait: { key: "verdictWait", style: "bg-green-100 text-green-950 ring-green-400" },
};

function WaterBalanceCard({ wb }: { wb: WaterBalance }) {
  const { t } = useI18n();
  const verdict = VERDICT[wb.verdict as "irrigate_now" | "wait"];
  const reach =
    wb.verdict === "irrigate_now" || wb.depletion_mm == null
      ? null
      : wb.days_to_raw == null
        ? t("notWithin")
        : wb.days_to_raw === 0
          ? t("today")
          : `${wb.days_to_raw} ${t("daysShort")}`;
  return (
    <Card className="ring-amber-300" >
      <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-stone-600">🧮 {t("calculatedTitle")}</h2>
      {verdict && (
        <p className={`mb-3 inline-block rounded-full px-4 py-1.5 text-lg font-bold ring-2 ${verdict.style}`}>{t(verdict.key)}</p>
      )}
      <dl className="grid grid-cols-2 gap-3 text-base">
        <div>
          <dt className="text-stone-600">{t("deficit")}</dt>
          <dd className="text-xl font-bold">{wb.depletion_mm} mm</dd>
        </div>
        <div>
          <dt className="text-stone-600">{t("limit")}</dt>
          <dd className="text-xl font-bold">{wb.raw_mm} mm</dd>
        </div>
        {reach && (
          <div className="col-span-2">
            <dt className="text-stone-600">{t("daysToLimit")}</dt>
            <dd className="text-xl font-bold">{reach}</dd>
          </div>
        )}
      </dl>
      <p className="mt-3 text-sm text-stone-700">{t("estimateNote")}</p>
      {wb.assumptions.length > 0 && (
        <details className="mt-2 text-sm text-stone-700">
          <summary className="cursor-pointer font-semibold">{t("assumptions")}</summary>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {wb.assumptions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </details>
      )}
      {/* CC BY 4.0 requires the weather source to be credited where its data is shown. */}
      {wb.data_source && <p className="mt-2 text-xs text-stone-600">{wb.data_source}</p>}
    </Card>
  );
}

function LabelCard({ entry }: { entry: LabelEntry }) {
  const { t } = useI18n();
  const unit = entry.dose_formulation_unit;
  return (
    <Card className="ring-2 ring-green-700" >
      <h2 className="mb-1 text-sm font-bold uppercase tracking-wide text-stone-600">🏷️ {t("labelTitle")}</h2>
      <p className="text-lg font-bold">{entry.formulation}</p>
      <p className="mb-3 text-sm text-stone-700">
        {entry.crop} · {entry.pest}
      </p>
      <dl className="grid grid-cols-2 gap-3">
        <div>
          <dt className="text-stone-600">{t("labelDose")}</dt>
          <dd className="text-xl font-bold">
            {entry.dose_formulation} {unit}
          </dd>
        </div>
        <div>
          <dt className="text-stone-600">{t("labelWait")}</dt>
          <dd className="text-xl font-bold">
            {entry.waiting_period_days} {t("daysShort")}
          </dd>
        </div>
        {entry.dilution_l_per_ha != null && (
          <div className="col-span-2">
            <dt className="text-stone-600">{t("labelDilution")}</dt>
            <dd className="text-lg font-bold">{entry.dilution_l_per_ha} L</dd>
          </div>
        )}
      </dl>
      <p className="mt-3 text-sm text-stone-700">
        {t("labelSource")}: {entry.source_ref} · {entry.label_date}
      </p>
      <p className="mt-2 rounded-lg bg-amber-50 p-2 text-sm font-semibold text-amber-950">{t("labelDisclaimer")}</p>
    </Card>
  );
}

function Sources({ items }: { items: EvidenceItem[] }) {
  const { t } = useI18n();
  return (
    <Card className="bg-stone-50">
      <h2 className="mb-1 text-sm font-bold uppercase tracking-wide text-stone-600">📄 {t("sourcesTitle")}</h2>
      <p className="mb-3 text-sm text-stone-700">{t("sourcesNote")}</p>
      <ul className="space-y-3">
        {items.map((e) => (
          <li key={e.chunk_id} className="border-l-4 border-stone-300 pl-3">
            <blockquote className="text-base italic text-stone-800">“{e.quote}”</blockquote>
            <p className="mt-1 text-sm text-stone-700">
              <a className="underline" href={e.url} target="_blank" rel="noreferrer noopener">
                {e.doc_title}
              </a>
              {e.source_org && `, ${e.source_org}`}
              {e.published_year && ` (${e.published_year})`}
              {e.page != null && ` · p. ${e.page}`} · {e.licence}
            </p>
          </li>
        ))}
      </ul>
    </Card>
  );
}
