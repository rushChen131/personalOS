"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSessionRestore } from "@/hooks/useSession";
import { useAuthStore } from "@/stores/auth";
import { LoginPanel } from "@/components/LoginPanel";
import { CopilotPanel } from "@/components/CopilotPanel";
import { LOCALES, useHydrateLocale, useLocaleStore, useT } from "@/lib/i18n";

const NAV = [{ href: "/dashboard", key: "nav.dashboard" }];

/** Segmented zh/en switch. Lives in the sidebar and on the login screen. */
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
  const logout = useAuthStore((state) => state.logout);
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

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-56 shrink-0 flex-col border-r border-surface-border bg-surface px-3 py-5">
        {/* Settings has no nav entry any more — the account block is the way in. */}
        <Link
          href="/settings"
          title={t("nav.settings")}
          aria-label={t("nav.settings")}
          className={`mb-5 block rounded-md px-2 py-2 transition-colors ${
            pathname.startsWith("/settings") ? "bg-accent-soft" : "hover:bg-surface-muted"
          }`}
        >
          <p className="text-base font-semibold">PersonalOS</p>
          <p className="mt-0.5 text-xs text-ink-muted">{user?.name}</p>
        </Link>
        <nav className="flex flex-1 flex-col gap-0.5">
          {NAV.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-md px-3 py-2 text-sm transition-colors ${
                  active ? "bg-accent-soft font-medium text-accent" : "text-ink-muted hover:bg-surface-muted"
                }`}
              >
                {t(item.key)}
              </Link>
            );
          })}
        </nav>
        <div className="mt-4 space-y-2">
          <LanguageToggle className="w-full justify-center" />
          <button
            type="button"
            onClick={logout}
            className="w-full rounded-md px-3 py-2 text-left text-sm text-ink-muted hover:bg-surface-muted"
          >
            {t("shell.signOut")}
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-x-hidden p-6">{children}</main>
      {copilotOpen ? null : (
        <button
          type="button"
          onClick={() => setCopilotOpen(true)}
          className="fixed right-4 top-4 z-10 rounded-md border border-surface-border bg-surface px-3 py-2 text-xs text-ink-muted shadow-sm hover:bg-surface-muted"
        >
          {t("shell.copilot")}
        </button>
      )}
      <CopilotPanel open={copilotOpen} onClose={() => setCopilotOpen(false)} />
    </div>
  );
}
