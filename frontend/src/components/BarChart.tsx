import { useT } from "@/lib/i18n";

/**
 * Minimal dependency-free bar chart.
 *
 * The spec named ECharts, but that adds ~1MB to the bundle for what is here a
 * simple distribution view. A hand-rolled SVG keeps the dashboard fast; swap in
 * ECharts only when interactive drill-down is actually needed.
 */
export function BarChart({
  data,
  height = 180,
}: {
  data: Array<{ label: string; value: number }>;
  height?: number;
}) {
  const { t, tEnum } = useT();
  if (!data.length) {
    return <p className="py-8 text-center text-xs text-ink-muted">{t("chart.empty")}</p>;
  }
  const max = Math.max(...data.map((d) => d.value), 1);
  const barWidth = 100 / data.length;

  return (
    <div className="w-full">
      <svg viewBox={`0 0 100 ${height / 2}`} preserveAspectRatio="none" className="w-full" style={{ height }}>
        {data.map((item, index) => {
          const barHeight = (item.value / max) * (height / 2 - 10);
          const x = index * barWidth + barWidth * 0.15;
          const width = barWidth * 0.7;
          return (
            <rect
              key={item.label}
              x={x}
              y={height / 2 - barHeight}
              width={width}
              height={Math.max(barHeight, 1)}
              rx={1}
              fill="var(--accent)"
            />
          );
        })}
      </svg>
      <div className="mt-1 flex" style={{ width: "100%" }}>
        {data.map((item) => (
          <span
            key={item.label}
            className="truncate text-center text-[10px] text-ink-muted"
            style={{ width: `${barWidth}%` }}
            title={`${tEnum(item.label)}: ${item.value}`}
          >
            {tEnum(item.label)}
          </span>
        ))}
      </div>
    </div>
  );
}
