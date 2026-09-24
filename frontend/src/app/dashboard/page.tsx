"use client";

import { useState } from "react";
import Link from "next/link";
import { Badge, Card, EmptyState, ErrorState, Modal, StatTile } from "@/components/ui";
import {
  useCreateJournal,
  useCreateTodo,
  useDeleteTodo,
  useJournals,
  useMemories,
  useTodos,
  useUpdateTodo,
} from "@/hooks/useApi";
import { api } from "@/lib/api";
import { formatDate, formatRelative } from "@/lib/format";
import { CATEGORIES, useT } from "@/lib/i18n";
import type { Category, Memory } from "@/types/api";

/** Todos are paged so the card keeps a fixed height next to the journal list. */
const TODOS_PER_PAGE = 5;
/** How many recent journals the overview shows before you open the journals page. */
const RECENT_JOURNALS = 6;

// Shared control styles — one place to keep the three button weights consistent.
const INPUT =
  "w-full rounded-md border border-surface-border px-3 py-2 text-sm text-ink outline-none focus:border-accent";
const SELECT =
  "rounded-md border border-surface-border px-3 py-2 text-sm text-ink outline-none focus:border-accent";
const BTN_PRIMARY = "rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-60";
const BTN_GHOST =
  "rounded-md border border-surface-border px-4 py-2 text-sm text-ink-muted hover:bg-surface-muted";
/** Compact button that sits in a card header. */
const BTN_CARD = "shrink-0 rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white";
/** Small button at the end of a todo row. */
const BTN_ROW =
  "shrink-0 rounded-md border border-surface-border px-2 py-1 text-xs text-ink-muted hover:bg-surface-muted disabled:opacity-60";
/** The armed half of the two-step delete, shown only when a parent owns steps. */
const BTN_ROW_ARMED =
  "shrink-0 rounded-md border border-accent px-2 py-1 text-xs text-accent hover:bg-accent-soft disabled:opacity-60";

/** Empty string means "any category" — used by the memory filter. */
type CategoryFilter = Category | "";

export default function DashboardPage() {
  const { t, tEnum, tCategory } = useT();
  const journals = useJournals();
  const todos = useTodos();
  const memories = useMemories();
  const createTodo = useCreateTodo();
  const updateTodo = useUpdateTodo();
  const deleteTodo = useDeleteTodo();
  const createJournal = useCreateJournal();
  /**
   * A second instance rather than reusing `createTodo`: the step form lives
   * inline in a row, the modal lives in an overlay, and sharing one mutation
   * would let a failed step render its error inside the modal and vice versa.
   */
  const createStep = useCreateTodo();

  const [query, setQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>("");
  const [results, setResults] = useState<Memory[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  // Both creation forms are modals on the overview — there are no other pages.
  const [todoOpen, setTodoOpen] = useState(false);
  const [todoTitle, setTodoTitle] = useState("");
  const [todoCategory, setTodoCategory] = useState<Category>("OTHER");
  const [todoTargetDate, setTodoTargetDate] = useState("");
  const [todoPage, setTodoPage] = useState(0);

  /** Ids of parents whose steps are showing. Collapsed is the default. */
  const [expandedTodos, setExpandedTodos] = useState<ReadonlySet<string>>(new Set());
  /** The parent whose inline "add a step" form is open; only ever one. */
  const [stepParent, setStepParent] = useState<string | null>(null);
  const [stepTitle, setStepTitle] = useState("");
  /** The parent whose delete has been armed by a first click. */
  const [armedDelete, setArmedDelete] = useState<string | null>(null);

  const [journalOpen, setJournalOpen] = useState(false);
  const [journalTitle, setJournalTitle] = useState("");
  const [journalCategory, setJournalCategory] = useState<Category>("OTHER");
  const [journalContent, setJournalContent] = useState("");

  const shownMemories = results ?? memories.data ?? [];

  const todoRows = todos.data ?? [];
  const openTodos = todoRows.filter((todo) => todo.completed_at === null).length;
  const doneTodos = todoRows.length - openTodos;
  const todoPageCount = Math.max(1, Math.ceil(todoRows.length / TODOS_PER_PAGE));
  // Clamp so deleting todos can never strand the view on an empty page.
  const currentTodoPage = Math.min(todoPage, todoPageCount - 1);
  const visibleTodos = todoRows.slice(
    currentTodoPage * TODOS_PER_PAGE,
    currentTodoPage * TODOS_PER_PAGE + TODOS_PER_PAGE,
  );

  function closeTodoModal() {
    setTodoOpen(false);
    setTodoTitle("");
    setTodoCategory("OTHER");
    setTodoTargetDate("");
    // Drop the previous failure so a reopened modal starts clean.
    createTodo.reset();
  }

  /** Check / uncheck. The server stamps `completed_at`; the client sends intent. */
  function toggleTodo(id: string, completed: boolean) {
    updateTodo.mutate({ id, completed });
  }

  function toggleExpanded(id: string) {
    setExpandedTodos((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  /** Open the inline step form for one parent, closing any other and expanding. */
  function openStepForm(parentId: string) {
    setStepParent(parentId);
    setStepTitle("");
    createStep.reset();
    // Reveal the steps so the new one is visible the moment it lands.
    setExpandedTodos((current) => new Set(current).add(parentId));
  }

  function closeStepForm() {
    setStepParent(null);
    setStepTitle("");
    createStep.reset();
  }

  /**
   * A step is title-only: the server copies `category` and `target_date` from
   * the parent, so nothing else is collected here.
   */
  function submitStep(parentId: string) {
    const title = stepTitle.trim();
    if (!title) return;
    createStep.mutate(
      { title, parent_id: parentId },
      {
        onSuccess: () => {
          setStepParent(null);
          setStepTitle("");
        },
      },
    );
  }

  /**
   * Deleting a parent takes its steps with it, so a parent that owns steps
   * needs a second click. A childless todo deletes on the first click, as before.
   */
  function requestDelete(todoId: string, stepCount: number) {
    if (stepCount === 0) {
      deleteTodo.mutate(todoId);
      return;
    }
    setArmedDelete(todoId);
  }

  function confirmDelete(todoId: string) {
    setArmedDelete(null);
    deleteTodo.mutate(todoId);
  }

  function closeJournalModal() {
    setJournalOpen(false);
    setJournalTitle("");
    setJournalCategory("OTHER");
    setJournalContent("");
    createJournal.reset();
  }

  /**
   * The memory card has one filter bar rather than two independent ones, so the
   * text query and the category always travel together. Called with explicit
   * overrides from the category select, which fires before state has settled.
   */
  async function runSearch(overrides?: { query?: string; category?: CategoryFilter }) {
    const nextQuery = (overrides?.query ?? query).trim();
    const nextCategory = overrides?.category ?? categoryFilter;
    if (!nextQuery && !nextCategory) {
      setResults(null);
      return;
    }
    setSearching(true);
    setSearchError(null);
    try {
      // Hybrid keyword + importance + recency search on the backend.
      setResults(
        await api.searchMemories({
          query: nextQuery || null,
          category: nextCategory || null,
        }),
      );
    } catch {
      setSearchError(t("memories.errorSearch"));
    } finally {
      setSearching(false);
    }
  }

  function clearSearch() {
    setQuery("");
    setCategoryFilter("");
    setResults(null);
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">{t("dashboard.title")}</h1>
          <p className="mt-0.5 text-sm text-ink-muted">{t("dashboard.subtitle")}</p>
        </div>
        <Link href="/reports" className={BTN_GHOST}>
          {t("dashboard.viewReports")}
        </Link>
      </header>

      {journals.isError ? <ErrorState message={t("dashboard.errorStats")} /> : null}

      <div className="grid grid-cols-3 gap-3 sm:gap-4">
        <StatTile label={t("dashboard.statJournals")} value={journals.data?.length ?? "—"} />
        <StatTile label={t("dashboard.statMemories")} value={memories.data?.length ?? "—"} />
        <StatTile label={t("dashboard.statOpenTodos")} value={todos.data ? openTodos : "—"} />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card
          title={t("dashboard.recentJournals")}
          subtitle={t("dashboard.recentJournalsHint")}
          action={
            <button type="button" onClick={() => setJournalOpen(true)} className={BTN_CARD}>
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
                    <span className="flex shrink-0 items-center gap-2">
                      <Badge>{tCategory(journal.category)}</Badge>
                      <span className="text-xs text-ink-muted">
                        {formatRelative(journal.occurred_at ?? journal.created_at)}
                      </span>
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
          title={t("todos.title")}
          subtitle={t("todos.summary", { open: openTodos, done: doneTodos })}
          action={
            <button type="button" onClick={() => setTodoOpen(true)} className={BTN_CARD}>
              {t("todos.newTodo")}
            </button>
          }
        >
          {todos.isLoading ? <EmptyState message={t("common.loading")} /> : null}
          {visibleTodos.length ? (
            <>
              <ul className="divide-y divide-surface-border">
                {visibleTodos.map((todo) => {
                  const done = todo.completed_at !== null;
                  const steps = todo.children;
                  const stepsDone = steps.filter((step) => step.completed_at !== null).length;
                  const expanded = expandedTodos.has(todo.id);
                  return (
                    <li key={todo.id} className="py-3">
                      <div className="flex items-start gap-3">
                        {/* Completion is the whole interaction: one checkbox, one truth. */}
                        <input
                          type="checkbox"
                          checked={done}
                          disabled={updateTodo.isPending}
                          onChange={(event) => toggleTodo(todo.id, event.target.checked)}
                          aria-label={t(done ? "todos.markOpen" : "todos.markDone")}
                          className="mt-1 h-4 w-4 shrink-0 accent-accent"
                        />
                        <div className="min-w-0 flex-1">
                          <p
                            className={`truncate text-sm font-medium ${done ? "text-ink-muted line-through" : ""}`}
                          >
                            {todo.title}
                          </p>
                          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                            <Badge>{tCategory(todo.category)}</Badge>
                            {todo.target_date ? (
                              <Badge>{t("todos.due", { date: formatDate(todo.target_date) })}</Badge>
                            ) : null}
                            {todo.completed_at ? (
                              <Badge>
                                {t("todos.completedAt", { date: formatDate(todo.completed_at) })}
                              </Badge>
                            ) : null}
                            {/* Only a parent can own steps, so this is also the disclosure. */}
                            {steps.length ? (
                              <button
                                type="button"
                                onClick={() => toggleExpanded(todo.id)}
                                aria-expanded={expanded}
                                aria-label={t(expanded ? "todos.collapse" : "todos.expand")}
                                className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs text-ink-muted hover:bg-surface-muted"
                              >
                                <span
                                  aria-hidden
                                  className={`inline-block transition-transform ${expanded ? "rotate-90" : ""}`}
                                >
                                  ▸
                                </span>
                                {t("todos.steps", { done: stepsDone, total: steps.length })}
                              </button>
                            ) : null}
                          </div>
                        </div>
                        <div className="flex shrink-0 items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => openStepForm(todo.id)}
                            aria-label={t("todos.addStep")}
                            title={t("todos.addStep")}
                            className={BTN_ROW}
                          >
                            +
                          </button>
                          {armedDelete === todo.id ? (
                            <>
                              <button
                                type="button"
                                onClick={() => confirmDelete(todo.id)}
                                disabled={deleteTodo.isPending}
                                className={BTN_ROW_ARMED}
                              >
                                {t("todos.confirmDeleteSteps", { count: steps.length })}
                              </button>
                              <button
                                type="button"
                                onClick={() => setArmedDelete(null)}
                                className={BTN_ROW}
                              >
                                {t("common.cancel")}
                              </button>
                            </>
                          ) : (
                            <button
                              type="button"
                              onClick={() => requestDelete(todo.id, steps.length)}
                              disabled={deleteTodo.isPending}
                              title={
                                steps.length
                                  ? t("todos.confirmDeleteSteps", { count: steps.length })
                                  : undefined
                              }
                              className={BTN_ROW}
                            >
                              {t("common.delete")}
                            </button>
                          )}
                        </div>
                      </div>

                      {expanded && steps.length ? (
                        <ul className="ml-7 mt-1 space-y-0.5 border-l border-surface-border pl-3">
                          {steps.map((step) => {
                            const stepDone = step.completed_at !== null;
                            return (
                              <li key={step.id} className="flex items-center gap-3 py-1">
                                {/* Independent of the parent, both ways (D1). */}
                                <input
                                  type="checkbox"
                                  checked={stepDone}
                                  disabled={updateTodo.isPending}
                                  onChange={(event) => toggleTodo(step.id, event.target.checked)}
                                  aria-label={t(stepDone ? "todos.markOpen" : "todos.markDone")}
                                  className="h-3.5 w-3.5 shrink-0 accent-accent"
                                />
                                {/* No badges: a step inherits category and date (D3). */}
                                <span
                                  className={`min-w-0 flex-1 truncate text-sm ${stepDone ? "text-ink-muted line-through" : "text-ink-muted"}`}
                                >
                                  {step.title}
                                </span>
                                <button
                                  type="button"
                                  onClick={() => deleteTodo.mutate(step.id)}
                                  disabled={deleteTodo.isPending}
                                  className="shrink-0 rounded-md px-1.5 py-0.5 text-xs text-ink-muted hover:bg-surface-muted disabled:opacity-60"
                                >
                                  {t("common.delete")}
                                </button>
                              </li>
                            );
                          })}
                        </ul>
                      ) : null}

                      {stepParent === todo.id ? (
                        <form
                          className="ml-7 mt-1.5 flex flex-wrap items-center gap-2"
                          onSubmit={(event) => {
                            event.preventDefault();
                            submitStep(todo.id);
                          }}
                        >
                          <input
                            autoFocus
                            value={stepTitle}
                            onChange={(event) => setStepTitle(event.target.value)}
                            placeholder={t("todos.stepPlaceholder")}
                            aria-label={t("todos.newStep")}
                            className="min-w-[10rem] flex-1 rounded-md border border-surface-border px-2 py-1 text-sm text-ink outline-none focus:border-accent"
                          />
                          <button
                            type="submit"
                            disabled={createStep.isPending}
                            className="rounded-md bg-accent px-2.5 py-1 text-xs font-medium text-white disabled:opacity-60"
                          >
                            {t("todos.addStep")}
                          </button>
                          <button type="button" onClick={closeStepForm} className={BTN_ROW}>
                            {t("common.cancel")}
                          </button>
                          <p className="w-full text-xs text-ink-muted">{t("todos.inheritHint")}</p>
                          {createStep.isError ? (
                            <p className="w-full text-xs text-ink-muted">
                              {t("todos.errorCreateStep")}
                            </p>
                          ) : null}
                        </form>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
              {todoPageCount > 1 ? (
                <div className="mt-3 flex items-center justify-between border-t border-surface-border pt-3 text-xs text-ink-muted">
                  <button
                    type="button"
                    disabled={currentTodoPage === 0}
                    onClick={() => setTodoPage(currentTodoPage - 1)}
                    className="rounded-md border border-surface-border px-2.5 py-1 disabled:opacity-40"
                  >
                    {t("common.prev")}
                  </button>
                  <span className="tabular-nums">
                    {t("common.pageOf", { page: currentTodoPage + 1, total: todoPageCount })}
                  </span>
                  <button
                    type="button"
                    disabled={currentTodoPage >= todoPageCount - 1}
                    onClick={() => setTodoPage(currentTodoPage + 1)}
                    className="rounded-md border border-surface-border px-2.5 py-1 disabled:opacity-40"
                  >
                    {t("common.next")}
                  </button>
                </div>
              ) : null}
            </>
          ) : (
            !todos.isLoading && <EmptyState message={t("todos.empty")} />
          )}
          {updateTodo.isError || deleteTodo.isError ? (
            <div className="mt-3">
              <ErrorState
                message={t(updateTodo.isError ? "todos.errorUpdate" : "todos.errorDelete")}
              />
            </div>
          ) : null}
        </Card>
      </div>

      <Card
        title={results ? t("memories.searchResults", { count: results.length }) : t("memories.allMemories")}
        subtitle={t("memories.derivedHint")}
      >
        {/* Search and category share one bar so the list and its filters stay together. */}
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void runSearch();
          }}
        >
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("memories.searchPlaceholder")}
            className={`min-w-[12rem] flex-1 ${INPUT}`}
          />
          <select
            value={categoryFilter}
            onChange={(event) => {
              const next = event.target.value as CategoryFilter;
              setCategoryFilter(next);
              // Apply immediately: a select that needs a submit feels broken.
              void runSearch({ category: next });
            }}
            aria-label={t("common.type")}
            className={SELECT}
          >
            <option value="">{t("memories.allCategories")}</option>
            {CATEGORIES.map((item) => (
              <option key={item} value={item}>
                {tCategory(item)}
              </option>
            ))}
          </select>
          <button type="submit" disabled={searching} className={BTN_PRIMARY}>
            {searching ? t("common.searching") : t("common.search")}
          </button>
          {results ? (
            <button type="button" onClick={clearSearch} className={BTN_GHOST}>
              {t("common.clear")}
            </button>
          ) : null}
        </form>
        {searchError ? (
          <div className="mt-3">
            <ErrorState message={searchError} />
          </div>
        ) : null}

        {memories.isLoading && !results ? <EmptyState message={t("common.loading")} /> : null}
        {shownMemories.length ? (
          <ul className="mt-4 divide-y divide-surface-border border-t border-surface-border">
            {shownMemories.map((memory) => (
              <li key={memory.id} className="flex items-start justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="text-sm">{memory.summary || memory.content}</p>
                  <p className="mt-0.5 text-xs text-ink-muted">
                    {t("memories.importance")} {memory.importance.toFixed(2)} · {formatRelative(memory.created_at)}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <Badge>{tCategory(memory.category)}</Badge>
                  <Badge>{tEnum(memory.type)}</Badge>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          !memories.isLoading && (
            <EmptyState message={results ? t("memories.noMatches") : t("memories.empty")} />
          )
        )}
      </Card>

      <Modal open={todoOpen} title={t("todos.newTodo")} onClose={closeTodoModal}>
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (!todoTitle.trim()) return;
            createTodo.mutate(
              {
                title: todoTitle.trim(),
                category: todoCategory,
                target_date: todoTargetDate || undefined,
              },
              {
                onSuccess: () => {
                  setTodoTitle("");
                  setTodoCategory("OTHER");
                  setTodoTargetDate("");
                  setTodoPage(0);
                  setTodoOpen(false);
                },
              },
            );
          }}
        >
          <label className="block text-xs text-ink-muted">
            {t("common.title")}
            <input
              value={todoTitle}
              onChange={(event) => setTodoTitle(event.target.value)}
              placeholder={t("todos.placeholder")}
              className={`mt-1 ${INPUT}`}
            />
          </label>
          <label className="block text-xs text-ink-muted">
            {t("common.type")}
            <select
              value={todoCategory}
              onChange={(event) => setTodoCategory(event.target.value as Category)}
              className={`mt-1 w-full ${SELECT}`}
            >
              {CATEGORIES.map((item) => (
                <option key={item} value={item}>
                  {tCategory(item)}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs text-ink-muted">
            {t("todos.targetDate")}
            <input
              type="date"
              value={todoTargetDate}
              onChange={(event) => setTodoTargetDate(event.target.value)}
              className={`mt-1 ${INPUT}`}
            />
          </label>
          {createTodo.isError ? <ErrorState message={t("todos.errorCreate")} /> : null}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={closeTodoModal} className={BTN_GHOST}>
              {t("common.cancel")}
            </button>
            <button type="submit" disabled={createTodo.isPending} className={BTN_PRIMARY}>
              {createTodo.isPending ? t("common.saving") : t("todos.addTodo")}
            </button>
          </div>
        </form>
      </Modal>

      <Modal open={journalOpen} title={t("journals.newEntry")} onClose={closeJournalModal}>
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (!journalTitle.trim() || !journalContent.trim()) return;
            createJournal.mutate(
              {
                title: journalTitle.trim(),
                content: journalContent.trim(),
                category: journalCategory,
              },
              {
                onSuccess: () => {
                  setJournalTitle("");
                  setJournalCategory("OTHER");
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
            className={INPUT}
          />
          <label className="block text-xs text-ink-muted">
            {t("common.type")}
            <select
              value={journalCategory}
              onChange={(event) => setJournalCategory(event.target.value as Category)}
              className={`mt-1 w-full ${SELECT}`}
            >
              {CATEGORIES.map((item) => (
                <option key={item} value={item}>
                  {tCategory(item)}
                </option>
              ))}
            </select>
          </label>
          <textarea
            value={journalContent}
            onChange={(event) => setJournalContent(event.target.value)}
            rows={5}
            placeholder={t("journals.entryContent")}
            className={`resize-y ${INPUT}`}
          />
          {createJournal.isError ? <ErrorState message={t("journals.errorSave")} /> : null}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={closeJournalModal} className={BTN_GHOST}>
              {t("common.cancel")}
            </button>
            <button type="submit" disabled={createJournal.isPending} className={BTN_PRIMARY}>
              {createJournal.isPending ? t("common.saving") : t("journals.saveEntry")}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
