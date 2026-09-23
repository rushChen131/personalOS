"use client";

import { useState } from "react";
import { useAuthStore } from "@/stores/auth";
import { useT } from "@/lib/i18n";

export function LoginPanel() {
  const { t } = useT();
  const login = useAuthStore((state) => state.login);
  const error = useAuthStore((state) => state.error);
  const loading = useAuthStore((state) => state.status === "loading");
  // The backend seeds this account on first boot (SEED_DEMO_USER=true).
  const [email, setEmail] = useState("demo@personalos.local");
  const [password, setPassword] = useState("demo1234");

  return (
    <form
      className="w-full max-w-sm rounded-xl border border-surface-border bg-surface p-6 shadow-sm"
      onSubmit={(event) => {
        event.preventDefault();
        void login(email, password);
      }}
    >
      <h1 className="text-lg font-semibold">{t("login.title")}</h1>
      <p className="mt-1 text-xs text-ink-muted">{t("login.hint")}</p>

      <label className="mt-5 block text-xs font-medium text-ink-muted" htmlFor="email">
        {t("login.email")}
      </label>
      <input
        id="email"
        type="email"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        className="mt-1 w-full rounded-md border border-surface-border px-3 py-2 text-sm outline-none focus:border-accent"
      />

      <label className="mt-4 block text-xs font-medium text-ink-muted" htmlFor="password">
        {t("login.password")}
      </label>
      <input
        id="password"
        type="password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        className="mt-1 w-full rounded-md border border-surface-border px-3 py-2 text-sm outline-none focus:border-accent"
      />

      {error ? <p className="mt-3 text-xs text-red-600">{error}</p> : null}

      <button
        type="submit"
        disabled={loading}
        className="mt-5 w-full rounded-md bg-accent px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
      >
        {loading ? t("login.submitting") : t("login.submit")}
      </button>
    </form>
  );
}
