"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Badge, Card, EmptyState, ErrorState, ProgressBar } from "@/components/ui";
import { useGoal } from "@/hooks/useApi";
import { formatDate } from "@/lib/format";
import { useT } from "@/lib/i18n";

export default function GoalDetailPage() {
  const { t, tEnum } = useT();
  const params = useParams<{ id: string }>();
  const goal = useGoal(params.id);

  if (goal.isLoading) {
    return <EmptyState message={t("goals.loadingOne")} />;
  }
  if (goal.isError || !goal.data) {
    return <ErrorState message={t("goals.notFound")} />;
  }

  const item = goal.data;
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <header className="space-y-1">
        <Link href="/goals" className="text-xs text-ink-muted hover:text-accent">
          ← {t("goals.title")}
        </Link>
        <div className="flex items-start justify-between gap-3">
          <h1 className="text-lg font-semibold">{item.title}</h1>
          <Badge>{tEnum(item.status)}</Badge>
        </div>
        {item.description ? <p className="text-sm text-ink-muted">{item.description}</p> : null}
      </header>

      <Card title={t("goals.progress")}>
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-ink-muted">
            <span>{t("goals.completion")}</span>
            <span className="tabular-nums">{Math.round(item.progress)}%</span>
          </div>
          <ProgressBar value={item.progress} />
        </div>
      </Card>

      <Card title={t("common.details")}>
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-xs text-ink-muted">{t("common.priority")}</dt>
            <dd className="mt-0.5">{tEnum(item.priority)}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-muted">{t("goals.targetDate")}</dt>
            <dd className="mt-0.5">{item.target_date ? formatDate(item.target_date) : "—"}</dd>
          </div>
        </dl>
      </Card>
    </div>
  );
}
