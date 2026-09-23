"use client";

import { Badge, Card, EmptyState } from "@/components/ui";
import { useInsights } from "@/hooks/useApi";
import { formatRelative } from "@/lib/format";
import { useT } from "@/lib/i18n";

export default function InsightsPage() {
  const { t, tEnum } = useT();
  const insights = useInsights();
  const rows = insights.data ?? [];

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <header>
        <h1 className="text-lg font-semibold">{t("insights.title")}</h1>
        <p className="mt-0.5 text-sm text-ink-muted">{t("insights.subtitle")}</p>
      </header>

      <Card title={t("insights.all", { count: rows.length })}>
        {insights.isLoading ? <EmptyState message={t("common.loading")} /> : null}
        {rows.length ? (
          <ul className="divide-y divide-surface-border">
            {rows.map((insight) => (
              <li key={insight.id} className="py-3">
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm font-medium">{insight.title}</p>
                  <Badge>{tEnum(insight.insight_type)}</Badge>
                </div>
                <p className="mt-1 text-sm text-ink-muted">{insight.content}</p>
                <p className="mt-1 text-xs text-ink-muted">
                  {t("insights.confidence")} {insight.confidence.toFixed(2)} · {formatRelative(insight.discovered_at)}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          !insights.isLoading && <EmptyState message={t("insights.empty")} />
        )}
      </Card>
    </div>
  );
}
