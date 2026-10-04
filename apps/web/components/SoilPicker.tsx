"use client";

import { useI18n } from "@/lib/i18n";
import type { MessageKey } from "@/lib/messages";
import type { SoilTexture } from "@/lib/types";

const OPTIONS: { value: SoilTexture; label: MessageKey; hint: MessageKey }[] = [
  { value: "sandy", label: "soilSandy", hint: "soilSandyHint" },
  { value: "loamy", label: "soilLoamy", hint: "soilLoamyHint" },
  { value: "clayey", label: "soilClayey", hint: "soilClayeyHint" },
];

/** The farmer's own words for soil (retili / domat / chikni), as big buttons: nobody needs
 *  a lab report to answer this (ADR-0015). "Not sure" is a real choice, not an error. */
export function SoilPicker({ value, onChange }: { value: SoilTexture | null; onChange: (v: SoilTexture | null) => void }) {
  const { t } = useI18n();
  return (
    <fieldset className="space-y-2">
      <legend className="text-base font-semibold text-stone-800">{t("soil")}</legend>
      <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label={t("soil")}>
        {OPTIONS.map((o) => {
          const selected = value === o.value;
          return (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => onChange(o.value)}
              className={`min-h-16 rounded-xl p-2 text-center font-semibold ring-2 transition-colors ${
                selected ? "bg-green-800 text-white ring-green-800" : "bg-white text-stone-900 ring-stone-300 hover:ring-green-700"
              }`}
            >
              <span className="block text-lg">{t(o.label)}</span>
              <span className={`block text-sm font-normal ${selected ? "text-green-100" : "text-stone-600"}`}>{t(o.hint)}</span>
            </button>
          );
        })}
      </div>
      <button
        type="button"
        onClick={() => onChange(null)}
        className={`min-h-12 w-full rounded-xl px-3 text-base ring-1 ${
          value === null ? "bg-stone-200 font-semibold ring-stone-400" : "bg-white ring-stone-300"
        }`}
      >
        {t("soilLater")}
      </button>
    </fieldset>
  );
}
