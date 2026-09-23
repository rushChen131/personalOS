"use client";

import { useState } from "react";
import Link from "next/link";
import { Badge, Card, EmptyState, ErrorState, Modal, ProgressBar, StatTile } from "@/components/ui";
import { useCreateGoal, useCreateJournal, useGoals, useJournals, useMemories } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { formatDate, formatRelative } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { Memory } from "@/types/api";

/** Goals are paged in the overview so the card stays a fixed height. */
const GOALS_PER_PAGE = 5;
/** How many recent journals the overview shows before you open the journals page. */
const RECENT_JOURNALS = 6;

export default function DashboardPage() {
  const { t, tEnum } = useT();
  const journals = useJournals();
  const goals = useGoals();
  const memories = useMemories();
  const createGoal = useCreateGoal();
  const createJournal = useCreateJournal();

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Memory[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [goalTitle, setGoalTitle] = useState("");
  const [goalTargetDate, setGoalTargetDate] = useState("");
  const [goalPage, setGoalPage] = useState(0);

  // The Journals nav entry is gone, so writing an entry happens in a modal here.
  const [journalOpen, setJournalOpen] = useState(false);
  const [journalTitle, setJournalTitle] = useState("");
  const [journalContent, setJournalContent] = useState("");

  const activeGoals = goals.data?.filter((g) => g.status === "ACTIVE").length;
  const shownMemories = results ?? memories.data ?? [];

  const goalRows = goals.data ?? [];
  const goalPageCount = Math.max(1, Math.ceil(goalRows.length / GOALS_PER_PAGE));
  // Clamp so deleting goals can never strand the view on an empty page.
  const currentGoalPage = Math.min(goalPage, goalPageCount - 1);
  const visibleGoals = goalRows.slice(
    currentGoalPage * GOALS_PER_PAGE,
    currentGoalPage * GOALS_PER_PAGE + GOALS_PER_PAGE,
  );

  function closeJournalModal() {
    setJournalOpen(false);
    setJournalTitle("");
    setJournalContent("");
    // Drop the previous failure so a reopened modal starts clean.
    createJournal.reset();
  }

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
    <div className="mx-auto max-w-5xl space-y-5">
      <header>
        <h1 className="text-lg font-semibold">{t("dashboard.title")}</h1>
        <p className="mt-0.5 text-sm text-ink-muted">{t("dashboard.subtitle")}</p>
      </header>

      {journals.isError ? <ErrorState message={t("dashboard.errorStats")} /> : null}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        <StatTile label={t("dashboard.statJournals")} value={journals.data?.length ?? "—"} />
        <StatTile label={t("dashboard.statMemories")} value={memories.data?.length ?? "—"} />
        <StatTile label={t("dashboard.statActiveGoals")} value={activeGoals ?? "—"} />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card
          title={t("dashboard.recentJournals")}
          subtitle={t("dashboard.recentJournalsHint")}
          action={
            <button
              type="button"
              onClick={() => setJournalOpen(true)}
              className="shrink-0 rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white"
            >
              {t("journals.newEntry")}
            </button>
          }
        >
          {journals.isLoading ? <EmptyState message={t("common.loading")} /> : null}
          {journals.data?.length ? (
            <ul className="divide-y divide-surface-border">
              {journals.data.slice(0, RECENT_JOURNALS).map((journal) => (
                <li key={journal.id}>
                  {/* Deep link so the journals page opens the entry you clicked. */}
                  <Link
                    href={`/journals?id=${journal.id}`}
                    className="-mx-2 flex items-center justify-between gap-3 rounded-md px-2 py-2.5 text-sm hover:bg-surface-muted"
                  >
                    <span className="truncate">{journal.title || t("journals.entry")}</span>
                    <span className="shrink-0 text-xs text-ink-muted">
                      {formatRelative(journal.occurred_at ?? journal.created_at)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            !journals.isLoading && <EmptyState message={t("journals.empty")} />
          )}
        </Card>

        <Card
          title={t("goals.activeGoals")}
          subtitle={t("goals.total", { count: goalRows.length })}
        >
          {goals.isLoading ? <EmptyState message={t("common.loading")} /> : null}
          {visibleGoals.length ? (
            <>
              <ul className="divide-y divide-surface-border">
                {visibleGoals.map((goal) => (
                  <li key={goal.id} className="py-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="truncate text-sm font-medium">{goal.title}</p>
                      <div className="flex shrink-0 items-center gap-2">
                        {goal.target_date ? (
                          <Badge>{t("goals.due", { date: formatDate(goal.target_date) })}</Badge>
                        ) : null}
                        <Badge>{tEnum(goal.status)}</Badge>
                      </div>
                    </div>
                    <div className="mt-2 flex items-center gap-3">
                      <div className="flex-1">
                        <ProgressBar value={goal.progress} />
                      </div>
                      <span className="w-10 text-right text-xs tabular-nums text-ink-muted">
                        {Math.round(goal.progress)}%
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
              {goalPageCount > 1 ? (
                <div className="mt-3 flex items-center justify-between border-t border-surface-border pt-3 text-xs text-ink-muted">
                  <button
                    type="button"
                    disabled={currentGoalPage === 0}
                    onClick={() => setGoalPage(currentGoalPage - 1)}
                    className="rounded-md border border-surface-border px-2.5 py-1 disabled:opacity-40"
                  >
                    {t("common.prev")}
                  </button>
                  <span className="tabular-nums">
                    {t("common.pageOf", { page: currentGoalPage + 1, total: goalPageCount })}
                  </span>
                  <button
                    type="button"
                    disabled={currentGoalPage >= goalPageCount - 1}
                    onClick={() => setGoalPage(currentGoalPage + 1)}
                    className="rounded-md border border-surface-border px-2.5 py-1 disabled:opacity-40"
                  >
                    {t("common.next")}
                  </button>
                </div>
              ) : null}
            </>
          ) : (
            !goals.isLoading && <EmptyState message={t("goals.empty")} />
          )}
        </Card>
      </div>

      <Card title={t("goals.newGoal")}>
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (!goalTitle.trim()) return;
            createGoal.mutate(
              { title: goalTitle.trim(), target_date: goalTargetDate || undefined },
              {
                onSuccess: () => {
                  setGoalTitle("");
                  setGoalTargetDate("");
                  setGoalPage(0);
                },
              },
            );
          }}
        >
          <label className="flex-1 text-xs text-ink-muted">
            {t("common.title")}
            <input
              value={goalTitle}
              onChange={(event) => setGoalTitle(event.target.value)}
              placeholder={t("goals.placeholder")}
              className="mt-1 w-full rounded-md border border-surface-border px-3 py-2 text-sm text-ink outline-none focus:border-accent"
            />
          </label>
          <label className="text-xs text-ink-muted">
            {t("goals.targetDate")}
            <input
              type="date"
              value={goalTargetDate}
              onChange={(event) => setGoalTargetDate(event.target.value)}
              className="mt-1 block rounded-md border border-surface-border px-3 py-2 text-sm text-ink outline-none focus:border-accent"
            />
          </label>
          <button
            type="submit"
            disabled={createGoal.isPending}
            className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            {createGoal.isPending ? t("common.saving") : t("goals.addGoal")}
          </button>
        </form>
        {createGoal.isError ? (
          <div className="mt-3">
            <ErrorState message={t("goals.errorCreate")} />
          </div>
        ) : null}
      </Card>

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
        subtitle={t("memories.derivedHint")}
      >
        {memories.isLoading && !results ? <EmptyState message={t("common.loading")} /> : null}
        {shownMemories.length ? (
          <ul className="divide-y divide-surface-border">
            {shownMemories.map((memory) => (
              <li key={memory.id} className="flex items-start justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="text-sm">{memory.summary || memory.content}</p>
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

      <Modal open={journalOpen} title={t("journals.newEntry")} onClose={closeJournalModal}>
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (!journalTitle.trim() || !journalContent.trim()) return;
            createJournal.mutate(
              { title: journalTitle.trim(), content: journalContent.trim() },
              {
                onSuccess: () => {
                  setJournalTitle("");
                  setJournalContent("");
                  setJournalOpen(false);
                },
              },
            );
          }}
        >
          <input
            value={journalTitle}
            onChange={(event) => setJournalTitle(event.target.value)}
            placeholder={t("journals.entryTitle")}
            className="w-full rounded-md border border-surface-border px-3 py-2 text-sm outline-none focus:border-accent"
          />
          <textarea
            value={journalContent}
            onChange={(event) => setJournalContent(event.target.value)}
            rows={5}
            placeholder={t("journals.entryContent")}
            className="w-full resize-y rounded-md border border-surface-border px-3 py-2 text-sm outline-none focus:border-accent"
          />
          {createJournal.isError ? <ErrorState message={t("journals.errorSave")} /> : null}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={closeJournalModal}
              className="rounded-md border border-surface-border px-3 py-2 text-sm text-ink-muted"
            >
              {t("common.cancel")}
            </button>
            <button
              type="submit"
              disabled={createJournal.isPending}
              className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              {createJournal.isPending ? t("common.saving") : t("journals.saveEntry")}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
