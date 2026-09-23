"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Badge, Card, EmptyState, ErrorState } from "@/components/ui";
import { useInsights } from "@/hooks/useApi";
import { useT } from "@/lib/i18n";

export default function InsightDetailPage() {
  const { t, tEnum } = useT();
  const params = useParams<{ id: string }>();
  const insights = useInsights();
  const insight = insights.data?.find((item) => item.id === params.id) ?? null;

  if (insights.isLoading) {
    return <EmptyState message={t("insights.loadingOne")} />;
  }
  if (!insight) {
    return <ErrorState message={t("insights.notFound")} />;
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <header className="space-y-1">
        <Link href="/insights" className="text-xs text-ink-muted hover:text-accent">
          ← {t("insights.title")}
        </Link>
        <div className="flex items-start justify-between gap-3">
          <h1 className="text-lg font-semibold">{insight.title}</h1>
          <Badge>{tEnum(insight.insight_type)}</Badge>
        </div>
      </header>

      <Card title={t("common.content")}>
        <p className="text-sm">{insight.content}</p>
        <p className="mt-3 text-xs text-ink-muted">
          {t("insights.confidence")} {insight.confidence.toFixed(2)}
        </p>
      </Card>
    </div>
  );
}
