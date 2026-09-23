"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Card, EmptyState } from "@/components/ui";
import { useJournals } from "@/hooks/useApi";
import { formatRelative } from "@/lib/format";
import { useT } from "@/lib/i18n";

/**
 * Reading view for journals. Writing one happens on the overview (a modal there),
 * so this page only lists and displays entries.
 */
function JournalsView() {
  const { t } = useT();
  const journals = useJournals();
  // The overview deep-links at a specific entry (`/journals?id=…`).
  const requested = useSearchParams().get("id");
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    if (requested) setSelected(requested);
  }, [requested]);

  const active =
    journals.data?.find((journal) => journal.id === selected) ?? journals.data?.[0] ?? null;

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <header>
        <h1 className="text-lg font-semibold">{t("journals.title")}</h1>
        <p className="mt-0.5 text-sm text-ink-muted">{t("journals.subtitle")}</p>
      </header>

      <div className="grid gap-5 lg:grid-cols-[280px_1fr]">
        <Card title={t("journals.allEntries")}>
          {journals.isLoading ? <EmptyState message={t("common.loading")} /> : null}
          {journals.data?.length ? (
            <ul className="space-y-1">
              {journals.data.map((journal) => (
                <li key={journal.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(journal.id)}
                    className={`w-full rounded-md px-2.5 py-2 text-left text-sm ${
                      active?.id === journal.id ? "bg-accent-soft text-accent" : "hover:bg-surface-muted"
                    }`}
                  >
                    <span className="block truncate">{journal.title}</span>
                    <span className="mt-0.5 block text-xs text-ink-muted">{formatRelative(journal.created_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            !journals.isLoading && <EmptyState message={t("journals.empty")} />
          )}
        </Card>

        <Card title={active?.title ?? t("journals.entry")}>
          {active ? (
            <article className="whitespace-pre-wrap text-sm leading-relaxed">{active.content}</article>
          ) : (
            <EmptyState message={t("common.selectHint")} />
          )}
        </Card>
      </div>
    </div>
  );
}

export default function JournalsPage() {
  const { t } = useT();
  // `useSearchParams` needs a Suspense boundary to stay statically renderable.
  return (
    <Suspense fallback={<p className="py-6 text-center text-sm text-ink-muted">{t("common.loading")}</p>}>
      <JournalsView />
    </Suspense>
  );
}
