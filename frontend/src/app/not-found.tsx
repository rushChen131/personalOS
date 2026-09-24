"use client";

import Link from "next/link";
import { useT } from "@/lib/i18n";

/**
 * Rendered inside the root layout, so the header and the copilot panel stay put
 * and the user always has a way back.
 *
 * Without this file Next.js serves its own bare 404 — English-only, no chrome,
 * no navigation — which reads as a crash rather than as "that URL is gone".
 * The app was consolidated into a single dashboard, so a stale bookmark or a
 * back-button press is a realistic way to land here.
 */
export default function NotFound() {
  const { t } = useT();

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-2 text-center">
      <p className="text-3xl font-semibold text-ink-muted">404</p>
      <p className="max-w-sm text-sm text-ink-muted">{t("notFound.body")}</p>
      <Link
        href="/dashboard"
        className="mt-2 rounded-md bg-accent px-3 py-2 text-sm font-medium text-white"
      >
        {t("notFound.back")}
      </Link>
    </div>
  );
}
