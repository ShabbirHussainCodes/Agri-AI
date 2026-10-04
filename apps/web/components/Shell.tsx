"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useAuth } from "@/lib/auth";
import { KISAN_CALL_CENTRE } from "@/lib/config";
import { useI18n } from "@/lib/i18n";
import { Button } from "./ui";

export function Shell({ children }: { children: ReactNode }) {
  const { t, lang, setLang } = useI18n();
  const { session, signOut } = useAuth();
  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-xl flex-col">
      <header className="flex items-center justify-between gap-2 px-4 py-3">
        <Link href="/" className="text-xl font-bold text-green-900">
          🌾 AgriAI
        </Link>
        <div className="flex items-center gap-1">
          <Button variant="quiet" onClick={() => setLang(lang === "hi" ? "en" : "hi")}>
            {t("langToggle")}
          </Button>
          {session && (
            <Button variant="quiet" onClick={() => signOut()}>
              {t("logout")}
            </Button>
          )}
        </div>
      </header>
      <main className="flex-1 space-y-4 px-4 pb-8">{children}</main>
      <footer className="px-4 py-4 text-sm text-stone-700">
        {t("helpLine")}: <strong>{KISAN_CALL_CENTRE}</strong>
      </footer>
    </div>
  );
}
