"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSessionRestore } from "@/hooks/useSession";
import { useAuthStore } from "@/stores/auth";
import { LoginPanel } from "@/components/LoginPanel";
import { CopilotPanel } from "@/components/CopilotPanel";
import { LOCALES, useHydrateLocale, useLocaleStore, useT } from "@/lib/i18n";

/** Segmented zh/en switch. Lives in Settings and on the login screen. */
export function LanguageToggle({ className = "" }: { className?: string }) {
  const locale = useLocaleStore((state) => state.locale);
  const setLocale = useLocaleStore((state) => state.setLocale);
  const { t } = useT();

  return (
    <div
      role="group"
      aria-label={t("shell.language")}
      className={`inline-flex items-center gap-0.5 rounded-md border border-surface-border p-0.5 ${className}`}
    >
      {LOCALES.map((item) => (
        <button
          key={item.value}
          type="button"
          aria-pressed={locale === item.value}
          onClick={() => setLocale(item.value)}
          className={`rounded px-2 py-1 text-xs transition-colors ${
            locale === item.value ? "bg-accent-soft font-medium text-accent" : "text-ink-muted hover:bg-surface-muted"
          }`}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  useSessionRestore();
  useHydrateLocale();
  const { t } = useT();
  const status = useAuthStore((state) => state.status);
  const user = useAuthStore((state) => state.user);
  const pathname = usePathname();
  const [copilotOpen, setCopilotOpen] = useState(true);

  if (status === "anonymous") {
    return (
      <main className="relative flex min-h-screen items-center justify-center p-6">
        <LanguageToggle className="absolute right-6 top-6" />
        <LoginPanel />
      </main>
    );
  }

  if (status !== "authenticated") {
    return (
      <main className="flex min-h-screen items-center justify-center p-6">
        <p className="text-sm text-ink-muted">{t("shell.loading")}</p>
      </main>
    );
  }

  // The sidebar is gone. The account chip is the only navigation left and it
  // leads to Settings, where the language switch and sign-out now live.
  const initial = (user?.name ?? user?.email ?? "?").trim().charAt(0).toUpperCase();

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-surface-border bg-surface px-6 py-2.5">
        <p className="text-sm font-semibold">PersonalOS</p>
        <div className="flex items-center gap-2">
          {copilotOpen ? null : (
            <button
              type="button"
              onClick={() => setCopilotOpen(true)}
              className="rounded-md border border-surface-border px-3 py-1.5 text-xs text-ink-muted hover:bg-surface-muted"
            >
              {t("shell.copilot")}
            </button>
          )}
          <Link
            href="/settings"
            title={t("settings.title")}
            aria-label={t("settings.title")}
            className={`flex items-center gap-2 rounded-full border border-surface-border py-1 pl-1 pr-3 text-xs transition-colors ${
              pathname.startsWith("/settings") ? "bg-accent-soft text-accent" : "text-ink-muted hover:bg-surface-muted"
            }`}
          >
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent text-[11px] font-semibold text-white">
              {initial}
            </span>
            <span className="max-w-[10rem] truncate">{user?.name}</span>
          </Link>
        </div>
      </header>
      <div className="flex flex-1">
        <main className="flex-1 overflow-x-hidden p-6">{children}</main>
        <CopilotPanel open={copilotOpen} onClose={() => setCopilotOpen(false)} />
      </div>
    </div>
  );
}
