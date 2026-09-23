"use client";

import { useState } from "react";
import { Badge, Card, EmptyState, ErrorState, ProgressBar } from "@/components/ui";
import { useCreateGoal, useGoals } from "@/hooks/useApi";
import { formatDate } from "@/lib/format";
import { useT } from "@/lib/i18n";

export default function GoalsPage() {
  const { t, tEnum } = useT();
  const goals = useGoals();
  const createGoal = useCreateGoal();
  const [title, setTitle] = useState("");
  const [targetDate, setTargetDate] = useState("");

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <header>
        <h1 className="text-lg font-semibold">{t("goals.title")}</h1>
        <p className="mt-0.5 text-sm text-ink-muted">{t("goals.subtitle")}</p>
      </header>

      <Card title={t("goals.newGoal")}>
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (!title.trim()) return;
            createGoal.mutate(
              { title: title.trim(), target_date: targetDate || undefined },
              {
                onSuccess: () => {
                  setTitle("");
                  setTargetDate("");
                },
              },
            );
          }}
        >
          <label className="flex-1 text-xs text-ink-muted">
            {t("common.title")}
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder={t("goals.placeholder")}
              className="mt-1 w-full rounded-md border border-surface-border px-3 py-2 text-sm text-ink outline-none focus:border-accent"
            />
          </label>
          <label className="text-xs text-ink-muted">
            {t("goals.targetDate")}
            <input
              type="date"
              value={targetDate}
              onChange={(event) => setTargetDate(event.target.value)}
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

      <Card title={t("goals.activeGoals")} subtitle={t("goals.total", { count: goals.data?.length ?? 0 })}>
        {goals.data?.length ? (
          <ul className="divide-y divide-surface-border">
            {goals.data.map((goal) => (
              <li key={goal.id} className="py-3.5">
                <div className="flex items-center justify-between gap-3">
                  <p className="truncate text-sm font-medium">{goal.title}</p>
                  <div className="flex shrink-0 items-center gap-2">
                    {goal.target_date ? <Badge>{t("goals.due", { date: formatDate(goal.target_date) })}</Badge> : null}
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
        ) : (
          <EmptyState message={t("goals.empty")} />
        )}
      </Card>
    </div>
  );
}
