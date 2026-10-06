"use client";

import { createContext, useContext, type ReactNode } from "react";
import { useI18n } from "./i18n";
import type { Crop } from "./types";

/** The crop list the farm page already loads (name_en, name_hi), shared with the answer card.
 *  The API's answer carries only the English crop name from the database; looking the name up here
 *  shows the Hindi name in the Hindi UI, also for answers saved before this existed. */
const CropsContext = createContext<Crop[]>([]);

export function CropsProvider({ crops, children }: { crops: Crop[]; children: ReactNode }) {
  return <CropsContext.Provider value={crops}>{children}</CropsContext.Provider>;
}

/** The crop's name in the chosen language; unknown names are shown as they came. */
export function useCropName(nameEn: string | null | undefined): string | null {
  const crops = useContext(CropsContext);
  const { lang } = useI18n();
  if (!nameEn) return null;
  if (lang === "en") return nameEn;
  const match = crops.find((c) => c.name_en.trim().toLowerCase() === nameEn.trim().toLowerCase());
  return match?.name_hi ?? nameEn;
}
