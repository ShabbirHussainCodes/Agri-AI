"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AuthForm } from "@/components/AuthForm";
import { Shell } from "@/components/Shell";
import { Card, ErrorNote } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { authConfigured } from "@/lib/supabase";
import { useI18n } from "@/lib/i18n";
import type { Farm } from "@/lib/types";

export default function Home() {
  const { t } = useI18n();
  const { session, loading } = useAuth();
  return (
    <Shell>
      {!authConfigured ? (
        <ErrorNote>{t("configMissing")}</ErrorNote>
      ) : loading ? (
        <p>{t("loading")}</p>
      ) : session ? (
        <FarmList token={session.access_token} />
      ) : (
        <>
          <h1 className="text-2xl font-bold text-green-900">{t("tagline")}</h1>
          <AuthForm />
        </>
      )}
    </Shell>
  );
}

function FarmList({ token }: { token: string }) {
  const { t } = useI18n();
  const [farms, setFarms] = useState<Farm[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    api<Farm[]>("/farms", { token })
      .then(setFarms)
      .catch((e) => setError(e instanceof ApiError ? e : new ApiError(0, "network", "network")));
  }, [token]);

  return (
    <>
      <h1 className="text-2xl font-bold text-green-900">{t("myFarms")}</h1>
      {error && <ErrorNote>{t("networkFailed")}</ErrorNote>}
      {!error && farms === null && <p>{t("loading")}</p>}
      {farms?.length === 0 && <p>{t("noFarms")}</p>}
      <ul className="space-y-3">
        {farms?.map((f) => (
          <li key={f.id}>
            <Link href={`/farms/${f.id}`}>
              <Card className="text-lg font-semibold hover:bg-green-50">🌱 {f.name}</Card>
            </Link>
          </li>
        ))}
      </ul>
      <Link
        href="/farms/new"
        className="flex min-h-12 items-center justify-center rounded-xl bg-green-800 px-5 py-2 text-base font-semibold text-white hover:bg-green-900"
      >
        {t("addFarm")}
      </Link>
    </>
  );
}
