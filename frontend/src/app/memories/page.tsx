"use client";

import { useState } from "react";
import { Badge, Card, EmptyState, ErrorState } from "@/components/ui";
import { useMemories } from "@/hooks/useApi";
import { formatRelative } from "@/lib/format";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { Memory } from "@/types/api";

export default function MemoriesPage() {
  const { t, tEnum } = useT();
  const memories = useMemories();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Memory[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const shown = results ?? memories.data ?? [];

  async function runSearch(event: React.FormEvent) {
    event.preventDefault();
    if (!query.trim()) {
      setResults(null);
      return;
    }
    setSearching(true);
    setSearchError(null);
    try {
      // Hybrid keyword + importance + recency search on the backend.
      setResults(await api.searchMemories(query.trim()));
    } catch {
      setSearchError(t("memories.errorSearch"));
    } finally {
      setSearching(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <header>
        <h1 className="text-lg font-semibold">{t("memories.title")}</h1>
        <p className="mt-0.5 text-sm text-ink-muted">{t("memories.subtitle")}</p>
        <p className="mt-2 text-xs text-ink-muted">{t("memories.derivedHint")}</p>
      </header>

      <Card title={t("common.search")}>
        <form className="flex gap-3" onSubmit={runSearch}>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("memories.searchPlaceholder")}
            className="flex-1 rounded-md border border-surface-border px-3 py-2 text-sm outline-none focus:border-accent"
          />
          <button
            type="submit"
            disabled={searching}
            className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            {searching ? t("common.searching") : t("common.search")}
          </button>
          {results ? (
            <button
              type="button"
              onClick={() => {
                setResults(null);
                setQuery("");
              }}
              className="rounded-md border border-surface-border px-3 py-2 text-sm text-ink-muted"
            >
              {t("common.clear")}
            </button>
          ) : null}
        </form>
        {searchError ? (
          <div className="mt-3">
            <ErrorState message={searchError} />
          </div>
        ) : null}
      </Card>

      <Card
        title={results ? t("memories.searchResults", { count: results.length }) : t("memories.allMemories")}
      >
        {memories.isLoading && !results ? <EmptyState message={t("common.loading")} /> : null}
        {shown.length ? (
          <ul className="divide-y divide-surface-border">
            {shown.map((memory) => (
              <li key={memory.id} className="flex items-start justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="text-sm">{memory.content}</p>
                  <p className="mt-0.5 text-xs text-ink-muted">
                    {t("memories.importance")} {memory.importance.toFixed(2)} · {formatRelative(memory.created_at)}
                  </p>
                </div>
                <Badge>{tEnum(memory.type)}</Badge>
              </li>
            ))}
          </ul>
        ) : (
          !memories.isLoading && (
            <EmptyState message={results ? t("memories.noMatches") : t("memories.empty")} />
          )
        )}
      </Card>
    </div>
  );
}
