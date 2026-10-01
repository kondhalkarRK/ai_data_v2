import type { ExecutionMode } from "@/hooks/use-admin";
import { EXECUTION_MODES } from "@/hooks/use-admin";
import { CHART_SERIES } from "@/lib/design";

export const MODE_COLOR: Record<ExecutionMode, string> = {
  SCHEMA: CHART_SERIES.positive,
  LLM: CHART_SERIES.ai,
  HYBRID: CHART_SERIES.primary,
  CACHE: CHART_SERIES.secondary,
};

export const MODE_LABEL: Record<ExecutionMode, string> = {
  SCHEMA: "Schema",
  LLM: "LLM",
  HYBRID: "Hybrid",
  CACHE: "Cache",
};

export function ModeLegend() {
  return (
    <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
      {EXECUTION_MODES.map((mode) => (
        <span key={mode} className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm" style={{ backgroundColor: MODE_COLOR[mode] }} />
          {MODE_LABEL[mode]}
        </span>
      ))}
    </div>
  );
}

/** Donut of Schema vs LLM vs Hybrid vs Cache. */
export function ModeDonut({ data }: { data: Array<{ mode: ExecutionMode; count: number }> }) {
  const total = data.reduce((sum, item) => sum + item.count, 0);
  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;

  return (
    <div className="flex flex-wrap items-center gap-6">
      <svg viewBox="0 0 140 140" className="size-36 shrink-0" role="img" aria-label="Query distribution">
        <circle cx="70" cy="70" r={radius} fill="none" stroke="hsl(var(--muted))" strokeWidth="18" />
        {total > 0
          ? data.map((item) => {
              const length = (item.count / total) * circumference;
              const segment = (
                <circle
                  key={item.mode}
                  cx="70"
                  cy="70"
                  r={radius}
                  fill="none"
                  stroke={MODE_COLOR[item.mode]}
                  strokeWidth="18"
                  strokeDasharray={`${length} ${circumference - length}`}
                  strokeDashoffset={-offset}
                  transform="rotate(-90 70 70)"
                >
                  <title>{`${MODE_LABEL[item.mode]}: ${item.count}`}</title>
                </circle>
              );
              offset += length;
              return segment;
            })
          : null}
        <text x="70" y="66" textAnchor="middle" className="fill-foreground text-[22px] font-semibold">
          {total.toLocaleString()}
        </text>
        <text x="70" y="86" textAnchor="middle" className="fill-muted-foreground text-[10px]">
          questions
        </text>
      </svg>
      <ul className="min-w-40 flex-1 space-y-2 text-sm">
        {data.map((item) => (
          <li key={item.mode} className="flex items-center justify-between gap-3">
            <span className="inline-flex items-center gap-2">
              <span className="size-2.5 rounded-sm" style={{ backgroundColor: MODE_COLOR[item.mode] }} />
              {MODE_LABEL[item.mode]}
            </span>
            <span className="tabular-nums text-muted-foreground">
              {item.count.toLocaleString()}
              <span className="ml-2 inline-block w-10 text-right">
                {total ? `${Math.round((item.count / total) * 100)}%` : "0%"}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Stacked daily bars by execution mode. */
export function DailyTrend({
  data,
}: {
  data: Array<{ date: string } & Record<ExecutionMode, number>>;
}) {
  const width = 640;
  const height = 180;
  const padBottom = 20;
  const max = Math.max(1, ...data.map((d) => EXECUTION_MODES.reduce((s, m) => s + d[m], 0)));
  const slot = width / Math.max(data.length, 1);
  const bar = Math.max(Math.min(slot * 0.7, 22), 2);
  const labelEvery = Math.ceil(data.length / 8);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-48 w-full" role="img" aria-label="Daily query trend">
      <line x1="0" x2={width} y1={height - padBottom} y2={height - padBottom} stroke="hsl(var(--border))" />
      {data.map((day, index) => {
        let y = height - padBottom;
        const x = index * slot + (slot - bar) / 2;
        const total = EXECUTION_MODES.reduce((s, m) => s + day[m], 0);
        return (
          <g key={day.date}>
            <title>{`${day.date}: ${total} questions`}</title>
            {EXECUTION_MODES.map((mode) => {
              const h = (day[mode] / max) * (height - padBottom - 8);
              y -= h;
              return h > 0 ? (
                <rect key={mode} x={x} y={y} width={bar} height={h} rx="1.5" fill={MODE_COLOR[mode]} />
              ) : null;
            })}
            {index % labelEvery === 0 ? (
              <text
                x={x + bar / 2}
                y={height - 5}
                textAnchor="middle"
                className="fill-muted-foreground text-[10px]"
              >
                {day.date.slice(5)}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}

/** Horizontal stacked bars, one per user. */
export function UserBars({
  data,
}: {
  data: Array<{ user: string; total: number } & Record<ExecutionMode, number>>;
}) {
  const max = Math.max(1, ...data.map((d) => d.total));
  if (!data.length) return <p className="text-sm text-muted-foreground">No questions yet.</p>;
  return (
    <ul className="space-y-2.5">
      {data.map((row) => (
        <li key={row.user} className="space-y-1">
          <div className="flex justify-between text-xs">
            <span className="truncate font-medium text-foreground">{row.user}</span>
            <span className="tabular-nums text-muted-foreground">{row.total.toLocaleString()}</span>
          </div>
          <div className="flex h-2 overflow-hidden rounded-full bg-muted" style={{ width: `${(row.total / max) * 100}%` }}>
            {EXECUTION_MODES.map((mode) =>
              row[mode] ? (
                <span
                  key={mode}
                  title={`${MODE_LABEL[mode]}: ${row[mode]}`}
                  style={{ width: `${(row[mode] / row.total) * 100}%`, backgroundColor: MODE_COLOR[mode] }}
                />
              ) : null,
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
