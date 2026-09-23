"use client";

import { Card } from "@/components/ui";
import { useAuthStore } from "@/stores/auth";
import { LanguageToggle } from "@/components/AppShell";
import { LOCALES, useLocaleStore, useT } from "@/lib/i18n";

export default function SettingsPage() {
  const { t } = useT();
  const locale = useLocaleStore((state) => state.locale);
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <header>
        <h1 className="text-lg font-semibold">{t("settings.title")}</h1>
        <p className="mt-0.5 text-sm text-ink-muted">{t("settings.subtitle")}</p>
      </header>

      <Card title={t("settings.profile")}>
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-xs text-ink-muted">{t("settings.name")}</dt>
            <dd className="mt-0.5">{user?.name ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-muted">{t("settings.email")}</dt>
            <dd className="mt-0.5">{user?.email ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-muted">{t("settings.timezone")}</dt>
            <dd className="mt-0.5">{user?.timezone ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-muted">{t("settings.locale")}</dt>
            <dd className="mt-0.5">{LOCALES.find((item) => item.value === locale)?.label ?? locale}</dd>
          </div>
        </dl>
      </Card>

      <Card title={t("shell.language")}>
        <LanguageToggle />
      </Card>

      <Card title={t("settings.session")}>
        <button
          type="button"
          onClick={logout}
          className="rounded-md border border-surface-border px-4 py-2 text-sm text-ink-muted hover:bg-surface-muted"
        >
          {t("shell.signOut")}
        </button>
      </Card>
    </div>
  );
}
