"use client";

import { Card, EmptyState, ErrorState, ProgressBar, StatTile } from "@/components/ui";
import { useGoals, useInsights, useJournals, useMemories } from "@/hooks/useApi";
import { formatDate, formatRelative } from "@/lib/format";
import { useT } from "@/lib/i18n";

export default function DashboardPage() {
  const { t } = useT();
  const journals = useJournals();
  const goals = useGoals();
  const insights = useInsights();
  const memories = useMemories();

  const activeGoals = goals.data?.filter((g) => g.status === "ACTIVE").length;

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <header>
        <h1 className="text-lg font-semibold">{t("dashboard.title")}</h1>
        <p className="mt-0.5 text-sm text-ink-muted">{t("dashboard.subtitle")}</p>
      </header>

      {journals.isError ? <ErrorState message={t("dashboard.errorStats")} /> : null}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label={t("dashboard.statJournals")} value={journals.data?.length ?? "—"} />
        <StatTile label={t("dashboard.statMemories")} value={memories.data?.length ?? "—"} />
        <StatTile label={t("dashboard.statActiveGoals")} value={activeGoals ?? "—"} />
        <StatTile label={t("dashboard.statInsights")} value={insights.data?.length ?? "—"} />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title={t("dashboard.recentJournals")} subtitle={t("dashboard.recentJournalsHint")}>
          {journals.isLoading ? <EmptyState message={t("common.loading")} /> : null}
          {journals.data?.length ? (
            <ul className="divide-y divide-surface-border">
              {journals.data.slice(0, 6).map((journal) => (
                <li key={journal.id} className="flex items-center justify-between py-2.5 text-sm">
                  <span className="truncate">{journal.title || t("journals.entry")}</span>
                  <span className="shrink-0 text-xs text-ink-muted">
                    {formatRelative(journal.occurred_at ?? journal.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState message={t("journals.empty")} />
          )}
        </Card>

        <Card title={t("dashboard.goals")} subtitle={t("dashboard.goalsHint")}>
          {goals.isLoading ? <EmptyState message={t("common.loading")} /> : null}
          {goals.data?.length ? (
            <ul className="space-y-3">
              {goals.data.slice(0, 5).map((goal) => (
                <li key={goal.id}>
                  <div className="flex items-center justify-between text-sm">
                    <span className="truncate">{goal.title}</span>
                    <span className="tabular-nums text-xs text-ink-muted">{Math.round(goal.progress)}%</span>
                  </div>
                  <div className="mt-1.5">
                    <ProgressBar value={goal.progress} />
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState message={t("goals.empty")} />
          )}
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title={t("dashboard.recentMemories")} subtitle={t("dashboard.recentMemoriesHint")}>
          {memories.data?.length ? (
            <ul className="space-y-3">
              {memories.data.slice(0, 5).map((memory) => (
                <li key={memory.id} className="text-sm">
                  <p className="font-medium">{memory.summary || memory.content}</p>
                  <p className="mt-0.5 text-xs text-ink-muted">
                    {t("memories.importance")} {Math.round(memory.importance)}
                    {memory.valid_from ? ` · ${formatDate(memory.valid_from)}` : ""}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState message={t("memories.empty")} />
          )}
        </Card>

        <Card title={t("dashboard.aiInsights")} subtitle={t("dashboard.aiInsightsHint")}>
          {insights.data?.length ? (
            <ul className="space-y-3">
              {insights.data.slice(0, 5).map((insight) => (
                <li key={insight.id} className="text-sm">
                  <p className="font-medium">{insight.title}</p>
                  <p className="mt-0.5 text-xs text-ink-muted">{insight.content}</p>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState message={t("insights.empty")} />
          )}
        </Card>
      </div>
    </div>
  );
}
