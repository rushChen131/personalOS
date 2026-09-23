"use client";

import { useState } from "react";
import { Card, EmptyState, ErrorState } from "@/components/ui";
import { useCreateJournal, useJournals } from "@/hooks/useApi";
import { formatRelative } from "@/lib/format";
import { useT } from "@/lib/i18n";

export default function JournalsPage() {
  const { t } = useT();
  const journals = useJournals();
  const createJournal = useCreateJournal();
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [selected, setSelected] = useState<string | null>(null);

  const active = journals.data?.find((journal) => journal.id === selected) ?? journals.data?.[0] ?? null;

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <header>
        <h1 className="text-lg font-semibold">{t("journals.title")}</h1>
        <p className="mt-0.5 text-sm text-ink-muted">{t("journals.subtitle")}</p>
      </header>

      <Card title={t("journals.newEntry")}>
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (!title.trim() || !content.trim()) return;
            createJournal.mutate(
              { title: title.trim(), content: content.trim() },
              {
                onSuccess: () => {
                  setTitle("");
                  setContent("");
                },
              },
            );
          }}
        >
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder={t("journals.entryTitle")}
            className="w-full rounded-md border border-surface-border px-3 py-2 text-sm outline-none focus:border-accent"
          />
          <textarea
            value={content}
            onChange={(event) => setContent(event.target.value)}
            rows={5}
            placeholder={t("journals.entryContent")}
            className="w-full resize-y rounded-md border border-surface-border px-3 py-2 text-sm outline-none focus:border-accent"
          />
          <button
            type="submit"
            disabled={createJournal.isPending}
            className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            {createJournal.isPending ? t("common.saving") : t("journals.saveEntry")}
          </button>
        </form>
        {createJournal.isError ? (
          <div className="mt-3">
            <ErrorState message={t("journals.errorSave")} />
          </div>
        ) : null}
      </Card>

      <div className="grid gap-5 lg:grid-cols-[280px_1fr]">
        <Card title={t("journals.allEntries")}>
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
            <EmptyState message={t("journals.empty")} />
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
