/** Today's date in the phone's own time zone, as YYYY-MM-DD (what the API expects). */
export function todayLocal(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
}

/** Whole calendar days from a YYYY-MM-DD date to `today` (default: the phone's today).
 *  Counted on calendar dates, not on timestamps: new Date("2026-08-30") is midnight UTC, which is
 *  05:30 IST, so dividing a timestamp difference by a day read 35 instead of 36 on every night
 *  before 05:30 IST (found in the first live run, 2026-10-05). */
export function daysSince(isoDate: string, today: string = todayLocal()): number {
  const [y, m, d] = isoDate.split("-").map(Number);
  const [ty, tm, td] = today.split("-").map(Number);
  return Math.round((Date.UTC(ty, tm - 1, td) - Date.UTC(y, m - 1, d)) / 86_400_000);
}

export function formatDate(iso: string, lang: "hi" | "en"): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(lang === "hi" ? "hi-IN" : "en-IN", { day: "numeric", month: "short", year: "numeric" });
}
