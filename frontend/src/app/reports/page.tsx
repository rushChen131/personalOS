"use client";

import { useState } from "react";
import { Badge, Card, EmptyState, ErrorState, StatTile } from "@/components/ui";
import { useDeleteReport, useGenerateReport, useReports } from "@/hooks/useApi";
import { useT } from "@/lib/i18n";
import type { Report, ReportContent, ReportType } from "@/types/api";

const TYPES: ReportType[] = ["DAILY", "WEEKLY", "MONTHLY"];

/** Local calendar date as `YYYY-MM-DD`.
 *
 * `toISOString()` is UTC, which would put a late-evening entry on the wrong
 * day for anyone east of Greenwich. The backend has no `tzdata` so it cannot
 * do this itself — which is exactly why it accepts explicit bounds.
 */
function localIso(date: Date): string {
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return shifted.toISOString().slice(0, 10);
}

/** The period containing today, in the user's own timezone. */
function currentPeriod(type: ReportType): { start: string; end: string } {
  const now = new Date();
  if (type === "DAILY") return { start: localIso(now), end: localIso(now) };
  if (type === "WEEKLY") {
    // ISO weeks start on Monday: JS getDay() is Sunday-based.
    const offset = (now.getDay() + 6) % 7;
    const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - offset);
    const sunday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - offset + 6);
    return { start: localIso(monday), end: localIso(sunday) };
  }
  const first = new Date(now.getFullYear(), now.getMonth(), 1);
  const last = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  return { start: localIso(first), end: localIso(last) };
}

function periodLabel(report: Report): string {
  return report.period_start === report.period_end
    ? report.period_start
    : `${report.period_start} ~ ${report.period_end}`;
}

/**
 * Prose built from the stored stats, in the language currently selected.
 *
 * The API also stores a `summary`, but it is frozen at generation time in the
 * user's `User.locale` — which the language toggle never writes back. Rendering
 * the sentence here keeps it consistent with the toggle; the stored summary
 * still serves API and AI consumers.
 */
function narrative(report: Report, locale: string, t: (k: string, p?: Record<string, string | number>) => string, tCategory: (v: string | null | undefined) => string): string {
  const content = report.content;
  const period = periodLabel(report);
  const parts: string[] = [];

  parts.push(
    content.journal_count
      ? t("reports.summaryHead", { period, count: content.journal_count, days: content.active_days })
      : t("reports.summaryEmpty", { period }),
  );

  const categories = Object.entries(content.category_breakdown);
  if (categories.length) {
    const top = categories
      .slice(0, 3)
      .map(([key, count]) => `${tCategory(key)} ${count}`)
      .join(locale === "en" ? ", " : "、");
    parts.push(t("reports.summaryCategories", { top }));
  }
  const moods = Object.entries(content.mood_breakdown);
  if (moods.length) parts.push(t("reports.summaryMood", { mood: moods[0][0] }));
  if (content.todos.length) {
    const titles = content.todos
      .slice(0, 3)
      .map((todo) => `「${todo.title}」`)
      .join(locale === "en" ? ", " : "、");
    parts.push(t("reports.summaryTodos", { todos: titles }));
  }
  if (content.memories.length) {
    parts.push(t("reports.summaryMemories", { count: content.memories.length }));
  }
  return parts.join(locale === "en" ? " " : "");
}

/** Horizontal bars, scaled to the largest count. No chart dependency. */
function Breakdown({
  title,
  counts,
  label,
}: {
  title: string;
  counts: Record<string, number>;
  label: (value: string) => string;
}) {
  const entries = Object.entries(counts);
  if (!entries.length) return null;
  const max = Math.max(...entries.map(([, count]) => count));
  return (
    <div>
      <p className="mb-2 text-xs font-medium text-ink-muted">{title}</p>
      <ul className="space-y-1.5">
        {entries.map(([key, count]) => (
          <li key={key} className="flex items-center gap-2 text-xs">
            <span className="w-20 shrink-0 truncate text-ink-muted">{label(key)}</span>
            <span className="h-2 flex-1 overflow-hidden rounded-full bg-surface-muted">
              <span
                className="block h-full rounded-full bg-accent"
                style={{ width: `${Math.round((count / max) * 100)}%` }}
              />
            </span>
            <span className="w-6 shrink-0 text-right tabular-nums">{count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ReportDetail({ report }: { report: Report }) {
  const { t, tCategory, locale } = useT();
  const content: ReportContent = report.content;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge>{t(`reports.${report.type.toLowerCase()}`)}</Badge>
        <Badge>{report.dimension === "ALL" ? t("reports.scopeAll") : tCategory(report.dimension)}</Badge>
        <span className="text-xs text-ink-muted">{periodLabel(report)}</span>
      </div>

      <p className="text-sm leading-relaxed">{narrative(report, locale, t, tCategory)}</p>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label={t("reports.journalCount")} value={content.journal_count} />
        <StatTile label={t("reports.activeDays")} value={content.active_days} />
        <StatTile label={t("reports.todos")} value={content.todos.length} />
        <StatTile label={t("reports.memories")} value={content.memories.length} />
      </div>

      {content.journal_count ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <Breakdown title={t("reports.breakdown")} counts={content.category_breakdown} label={tCategory} />
          <Breakdown title={t("reports.moods")} counts={content.mood_breakdown} label={(value) => value} />
        </div>
      ) : (
        <p className="text-sm text-ink-muted">{t("reports.none")}</p>
      )}

      {content.todos.length ? (
        <div>
          <p className="mb-2 text-xs font-medium text-ink-muted">{t("reports.todos")}</p>
          <ul className="space-y-1">
            {content.todos.map((todo) => (
              <li key={todo.id} className="flex items-center justify-between gap-2 text-sm">
                <span className={`truncate ${todo.completed ? "text-ink-muted line-through" : ""}`}>
                  {todo.title}
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  <Badge>{tCategory(todo.category)}</Badge>
                  <Badge>{t(todo.completed ? "todos.completed" : "todos.open")}</Badge>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {content.memories.length ? (
        <div>
          <p className="mb-2 text-xs font-medium text-ink-muted">{t("reports.memories")}</p>
          <ul className="space-y-1.5">
            {content.memories.map((memory) => (
              <li key={memory.id} className="flex items-start gap-2 text-sm">
                <Badge>{tCategory(memory.category)}</Badge>
                <span className="min-w-0 flex-1">{memory.content}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {content.highlights.length ? (
        <div>
          <p className="mb-2 text-xs font-medium text-ink-muted">{t("reports.highlights")}</p>
          <ul className="space-y-2">
            {content.highlights.map((highlight) => (
              <li key={highlight.journal_id} className="rounded-md border border-surface-border p-2.5">
                <p className="text-sm font-medium">{highlight.title || t("journals.entry")}</p>
                <p className="mt-0.5 text-xs leading-relaxed text-ink-muted">{highlight.excerpt}</p>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

export default function ReportsPage() {
  const { t } = useT();
  const [type, setType] = useState<ReportType>("DAILY");
  const [selected, setSelected] = useState<string | null>(null);
  const reports = useReports(type);
  const generate = useGenerateReport();
  const remove = useDeleteReport();

  const active = reports.data?.find((report) => report.id === selected) ?? reports.data?.[0] ?? null;

  async function onGenerate() {
    const bounds = currentPeriod(type);
    const created = await generate.mutateAsync({
      type,
      period_start: bounds.start,
      period_end: bounds.end,
    });
    setSelected(created.id);
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <header>
        <h1 className="text-lg font-semibold">{t("reports.title")}</h1>
        <p className="mt-0.5 text-sm text-ink-muted">{t("reports.subtitle")}</p>
      </header>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="tablist" aria-label={t("reports.title")} className="inline-flex items-center gap-0.5 rounded-md border border-surface-border p-0.5">
          {TYPES.map((item) => (
            <button
              key={item}
              type="button"
              role="tab"
              aria-selected={type === item}
              onClick={() => {
                setType(item);
                setSelected(null);
              }}
              className={`rounded px-3 py-1.5 text-sm transition-colors ${
                type === item ? "bg-accent-soft font-medium text-accent" : "text-ink-muted hover:bg-surface-muted"
              }`}
            >
              {t(`reports.${item.toLowerCase()}`)}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => void onGenerate()}
          disabled={generate.isPending}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          {generate.isPending ? t("reports.generating") : t("reports.generate")}
        </button>
      </div>

      {generate.isError ? <ErrorState message={t("reports.errorGenerate")} /> : null}

      <div className="grid gap-5 lg:grid-cols-[300px_1fr]">
        <Card title={t(`reports.${type.toLowerCase()}`)}>
          {reports.isLoading ? <EmptyState message={t("common.loading")} /> : null}
          {reports.isError ? <ErrorState message={t("reports.errorLoad")} /> : null}
          {reports.data?.length ? (
            <ul className="space-y-1">
              {reports.data.map((report) => (
                <li key={report.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(report.id)}
                    className={`w-full rounded-md px-2.5 py-2 text-left text-sm ${
                      active?.id === report.id ? "bg-accent-soft text-accent" : "hover:bg-surface-muted"
                    }`}
                  >
                    <span className="block truncate">{report.title}</span>
                    <span className="mt-0.5 block text-xs text-ink-muted">
                      {t("reports.journalCount")}: {report.content.journal_count}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            !reports.isLoading && !reports.isError && <EmptyState message={t("reports.empty")} />
          )}
        </Card>

        <Card
          title={active ? active.title : t("reports.title")}
          action={
            active ? (
              <button
                type="button"
                onClick={() => {
                  remove.mutate(active.id);
                  setSelected(null);
                }}
                className="shrink-0 rounded-md border border-surface-border px-3 py-1.5 text-xs text-ink-muted hover:bg-surface-muted"
              >
                {t("reports.delete")}
              </button>
            ) : null
          }
        >
          {active ? <ReportDetail report={active} /> : <EmptyState message={t("reports.selectPrompt")} />}
        </Card>
      </div>
    </div>
  );
}
