"use client";

import { useState, type FormEvent } from "react";
import { useI18n } from "@/lib/i18n";
import { supabase } from "@/lib/supabase";
import { Button, Card, ErrorNote, Field, inputClass } from "./ui";

export function AuthForm() {
  const { t } = useI18n();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    const auth = supabase().auth;
    const { data, error: err } =
      mode === "login"
        ? await auth.signInWithPassword({ email, password })
        : await auth.signUp({ email, password });
    setBusy(false);
    if (err) setError(t("authFailed"));
    else if (mode === "signup" && !data.session) setNotice(t("checkEmail"));
    // On success the AuthProvider sees the new session and the page switches by itself.
  }

  return (
    <Card>
      <p className="mb-4 text-lg text-stone-800">{t("tagline")}</p>
      <form onSubmit={submit} className="space-y-4">
        <Field label={t("email")}>
          <input
            className={inputClass}
            type="email"
            inputMode="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
        <Field label={t("password")}>
          <input
            className={inputClass}
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            required
            minLength={6}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        {error && <ErrorNote>{error}</ErrorNote>}
        {notice && <p className="rounded-xl bg-green-50 p-3 text-green-900 ring-1 ring-green-200">{notice}</p>}
        <Button type="submit" disabled={busy} className="w-full">
          {mode === "login" ? t("login") : t("signup")}
        </Button>
      </form>
      <Button
        variant="quiet"
        className="mt-2 w-full"
        onClick={() => {
          setMode(mode === "login" ? "signup" : "login");
          setError(null);
          setNotice(null);
        }}
      >
        {mode === "login" ? t("toSignup") : t("toLogin")}
      </Button>
    </Card>
  );
}
