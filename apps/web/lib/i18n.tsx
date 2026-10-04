"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useSyncExternalStore, type ReactNode } from "react";
import { messages, type Lang, type MessageKey } from "./messages";

type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: (key: MessageKey) => string };

const I18nContext = createContext<Ctx | null>(null);
const STORAGE_KEY = "agriai.lang";

// The language lives in localStorage (a per-device convenience; the app works without it) and is
// read through useSyncExternalStore, so the server render and first client render both say Hindi
// and the saved choice then takes over without a hydration mismatch.
const listeners = new Set<() => void>();

function readLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "hi" || saved === "en") return saved;
  } catch {
    /* private mode: keep the default */
  }
  return "hi";
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const lang = useSyncExternalStore(subscribe, readLang, () => "hi" as Lang);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((l: Lang) => {
    try {
      localStorage.setItem(STORAGE_KEY, l);
    } catch {
      /* ignore */
    }
    listeners.forEach((cb) => cb());
  }, []);

  const value = useMemo<Ctx>(() => ({ lang, setLang, t: (key) => messages[key][lang] }), [lang, setLang]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): Ctx {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n outside I18nProvider");
  return ctx;
}
