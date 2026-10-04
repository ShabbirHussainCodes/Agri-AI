"use client";

import { useState } from "react";
import { formatDate } from "@/lib/dates";
import { useI18n } from "@/lib/i18n";
import type { MessageKey } from "@/lib/messages";
import { pickLanguage } from "@/lib/text";
import type { Activity, AdvisoryRecord, AdvisoryResponse } from "@/lib/types";
import { AnswerCard } from "./AnswerCard";
import { Button, Card } from "./ui";

export type DiaryItem =
  | { kind: "advisory"; at: string; record: AdvisoryRecord }
  | { kind: "activity"; at: string; activity: Activity };

export function buildDiary(activities: Activity[], advisories: AdvisoryRecord[]): DiaryItem[] {
  const items: DiaryItem[] = [
    ...activities.map((a): DiaryItem => ({ kind: "activity", at: a.occurred_on, activity: a })),
    ...advisories.map((r): DiaryItem => ({ kind: "advisory", at: r.created_at, record: r })),
  ];
  return items.sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));
}

const ACTIVITY_LABEL: Record<string, MessageKey> = {
  irrigation: "irrigation",
  fertiliser: "fertiliser",
  spray: "spray",
  sowing: "sowing",
  scouting: "scouting",
  other: "other",
};

/** The farm diary is the home surface (frontend-architecture.md): chat lives inside it. */
export function Diary({ items }: { items: DiaryItem[] }) {
  const { t } = useI18n();
  if (items.length === 0) return <p className="px-1 text-stone-700">{t("noDiary")}</p>;
  return (
    <ol className="space-y-3" aria-label={t("farmDiary")}>
      {items.map((item) =>
        item.kind === "activity" ? (
          <ActivityRow key={`a-${item.activity.id}`} activity={item.activity} />
        ) : (
          <AdvisoryRow key={`q-${item.record.id}`} record={item.record} />
        ),
      )}
    </ol>
  );
}

function ActivityRow({ activity }: { activity: Activity }) {
  const { t, lang } = useI18n();
  const depth = typeof activity.details?.depth_mm === "number" ? ` · ${activity.details.depth_mm} mm` : "";
  return (
    <li>
      <Card className="flex items-center gap-3">
        <span aria-hidden className="text-2xl">{activity.type === "irrigation" ? "💧" : "📝"}</span>
        <div>
          <p className="font-semibold">
            {t(ACTIVITY_LABEL[activity.type] ?? "other")}
            {depth}
          </p>
          <p className="text-sm text-stone-600">{formatDate(activity.occurred_on, lang)}</p>
        </div>
      </Card>
    </li>
  );
}

function AdvisoryRow({ record }: { record: AdvisoryRecord }) {
  const { t, lang } = useI18n();
  const [open, setOpen] = useState(false);
  // The stored response is whatever the API sent at the time (kept as a plain object so an
  // old row never fails to load), so treat it as an AdvisoryResponse only for display.
  const response = record.response as unknown as AdvisoryResponse;
  return (
    <li>
      <Card>
        <p className="text-sm text-stone-600">
          {t("question")} · {formatDate(record.created_at, lang)}
        </p>
        <p className="mb-2 text-lg font-semibold">{record.question}</p>
        {open ? (
          <AnswerCard r={response} />
        ) : (
          <p className="line-clamp-3 text-base text-stone-800">{pickLanguage(response.recommendation, lang)}</p>
        )}
        <Button variant="quiet" className="mt-1" onClick={() => setOpen(!open)}>
          {open ? t("hideAnswer") : t("showAnswer")}
        </Button>
      </Card>
    </li>
  );
}
