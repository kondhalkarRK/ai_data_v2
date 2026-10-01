"use client";

import {
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  CircleAlert,
  Database,
  ListChecks,
  Minus,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import type * as React from "react";

import { formatCount } from "@/components/executive/cockpit/format";
import type { Band, DataReliability, TrustFilters } from "@/components/reliability/types";
import {
  BAND_COLOUR,
  Card,
  cardClass,
  formatDelta,
  formatScore,
  formatWhen,
  Sparkline,
  TONE_COLOUR,
  TRUST,
} from "@/components/reliability/ui";
import { cn } from "@/lib/utils";

const START = 150;
const SWEEP = 240;
const BAND_SEGMENTS: Array<{ band: Band; from: number; to: number; label: string; range: string }> = [
  { band: "risk", from: 0, to: 70, label: "Risk", range: "< 70" },
  { band: "fair", from: 70, to: 85, label: "Fair", range: "70–85" },
  { band: "good", from: 85, to: 95, label: "Good", range: "85–95" },
  { band: "excellent", from: 95, to: 100, label: "Excellent", range: "95–100" },
];

function polar(cx: number, cy: number, r: number, angle: number): [number, number] {
  const rad = (angle * Math.PI) / 180;
  return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)];
}

function arc(cx: number, cy: number, r: number, from: number, to: number): string {
  const a = START + (SWEEP * from) / 100;
  const b = START + (SWEEP * to) / 100;
  const [x1, y1] = polar(cx, cy, r, a);
  const [x2, y2] = polar(cx, cy, r, b);
  return `M${x1.toFixed(2)},${y1.toFixed(2)} A${r},${r} 0 ${b - a > 180 ? 1 : 0} 1 ${x2.toFixed(2)},${y2.toFixed(2)}`;
}

export function TrustGauge({ score, band, size = 208 }: { score: number | null; band: Band; size?: number }) {
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 14;
  const value = score == null ? 0 : Math.max(0, Math.min(100, score));
  const [mx, my] = polar(cx, cy, r, START + (SWEEP * value) / 100);
  const colour = BAND_COLOUR[band];
  return (
    <svg
      width={size}
      height={size * 0.82}
      viewBox={`0 0 ${size} ${size * 0.82}`}
      data-chart
      role="img"
      aria-label={score == null ? "Trust score not available" : `Trust score ${score.toFixed(1)} of 100`}
    >
      {BAND_SEGMENTS.map((s) => (
        <path
          key={s.band}
          d={arc(cx, cy, r, s.from + (s.from ? 0.6 : 0), s.to - (s.to < 100 ? 0.6 : 0))}
          fill="none"
          stroke={BAND_COLOUR[s.band]}
          strokeOpacity={0.16}
          strokeWidth={12}
          strokeLinecap="butt"
        />
      ))}
      {score != null ? (
        <>
          <path d={arc(cx, cy, r, 0, value)} fill="none" stroke={colour} strokeWidth={12} strokeLinecap="round" />
          <circle cx={mx} cy={my} r={7.5} fill="#fff" stroke={colour} strokeWidth={3} />
        </>
      ) : null}
      {[70, 85, 95].map((tick) => {
        const [tx, ty] = polar(cx, cy, r - 19, START + (SWEEP * tick) / 100);
        return (
          <text key={tick} x={tx} y={ty} textAnchor="middle" dominantBaseline="middle" fontSize={9} fill="#94a3b8">
            {tick}
          </text>
        );
      })}
      <text x={cx} y={cy - 2} textAnchor="middle" fontSize={40} fontWeight={600} fill={TRUST.ink}>
        {formatScore(score)}
      </text>
      <text x={cx} y={cy + 20} textAnchor="middle" fontSize={11} fill="#64748b">
        out of 100
      </text>
    </svg>
  );
}

export function TrustHero({
  data,
  onFilter,
  onJump,
}: {
  data: DataReliability;
  onFilter: (patch: TrustFilters) => void;
  onJump: (section: "catalog" | "alerts" | "datasets" | "trend") => void;
}) {
  const { hero, summary } = data;
  const trend = data.trend.points.map((p) => p.score);
  const delta = hero.delta7d;
  const bandColour = BAND_COLOUR[hero.band];
  return (
    <div className="grid gap-4 xl:grid-cols-12">
      <Card className="relative overflow-hidden bg-gradient-to-br from-[#eef4ff] via-white to-[#eaf7f3] xl:col-span-4 dark:from-surface-raised dark:to-surface-raised">
        <div className="flex items-center justify-between">
          <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-slate-500">Enterprise trust score</p>
          <span
            className="rounded-full px-2.5 py-0.5 text-2xs font-semibold"
            style={{ backgroundColor: `${bandColour}1f`, color: bandColour }}
          >
            {hero.bandLabel}
          </span>
        </div>
        <div className="mt-1 flex flex-col items-center">
          <TrustGauge score={hero.score} band={hero.band} />
          {hero.available ? (
            <p className="-mt-3 flex items-center gap-1 text-xs text-slate-600">
              <DeltaIcon delta={delta} />
              <span className="font-semibold tabular-nums">{formatDelta(delta)}</span>
              <span className="text-slate-400">vs 7 days earlier</span>
            </p>
          ) : (
            <p className="-mt-2 max-w-xs text-center text-xs text-slate-500">{hero.unavailableReason}</p>
          )}
        </div>
        <div className="mt-4 grid grid-cols-4 gap-1.5">
          {BAND_SEGMENTS.slice()
            .reverse()
            .map((s) => (
              <div
                key={s.band}
                className={cn(
                  "rounded-lg px-1.5 py-1 text-center ring-1 ring-inset ring-transparent",
                  s.band === hero.band && "bg-white ring-slate-200 dark:bg-muted",
                )}
              >
                <p className="flex items-center justify-center gap-1 text-2xs font-medium text-slate-700 dark:text-foreground">
                  <span className="size-1.5 rounded-full" style={{ backgroundColor: BAND_COLOUR[s.band] }} />
                  {s.label}
                </p>
                <p className="text-[10px] tabular-nums text-slate-400">{s.range}</p>
              </div>
            ))}
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:col-span-5">
        <KpiTile
          icon={<ListChecks className="size-4" />}
          label="Active DQ rules"
          value={formatCount(hero.rulesActive)}
          foot={`${hero.rulesTotal} defined · ${formatCount(hero.recordsChecked)} records checked`}
          accent={TRUST.blue}
          onClick={() => {
            onFilter({ status: undefined });
            onJump("catalog");
          }}
        />
        <KpiTile
          icon={<CheckCircle2 className="size-4" />}
          label="Passing"
          value={formatCount(hero.rulesPassing)}
          foot={hero.rulesActive ? `${Math.round((hero.rulesPassing / hero.rulesActive) * 100)}% of active rules` : "—"}
          accent={TRUST.green}
          onClick={() => {
            onFilter({ status: "passing" });
            onJump("catalog");
          }}
        />
        <KpiTile
          icon={<CircleAlert className="size-4" />}
          label="Failing"
          value={formatCount(hero.rulesFailing)}
          foot={hero.rulesErrored ? `${hero.rulesErrored} could not run` : "below their target"}
          accent={hero.rulesFailing ? TRUST.amber : TRUST.grey}
          onClick={() => {
            onFilter({ status: "failing" });
            onJump("catalog");
          }}
        />
        <KpiTile
          icon={<ShieldAlert className="size-4" />}
          label="Critical issues"
          value={formatCount(hero.criticalIssues)}
          foot={hero.criticalIssues ? "need attention today" : "none open"}
          accent={hero.criticalIssues ? TRUST.coral : TRUST.green}
          onClick={() => {
            onFilter({ severity: "critical" });
            onJump("alerts");
          }}
        />
        <KpiTile
          icon={<Database className="size-4" />}
          label="Datasets monitored"
          value={formatCount(hero.datasetsMonitored)}
          foot={data.dataAsOf ? `data as of ${formatWhen(data.dataAsOf)}` : "across the warehouse"}
          accent={TRUST.teal}
          onClick={() => onJump("datasets")}
        />
        <KpiTile
          icon={<Sparkles className="size-4" />}
          label="Trust trend"
          value={formatDelta(delta)}
          foot="last 7 days"
          accent={delta != null && delta < -0.05 ? TRUST.amber : TRUST.green}
          spark={trend.slice(-30)}
          onClick={() => onJump("trend")}
        />
      </div>

      <Card className="flex flex-col xl:col-span-3">
        <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-[#2f6fed]">Executive trust summary</p>
        <p className="mt-1.5 text-sm font-semibold leading-snug text-slate-800 dark:text-foreground">{summary.headline}</p>
        <ul className="mt-3 flex-1 space-y-2.5">
          {summary.statements.map((s, i) => (
            <li key={i} className="flex gap-2 text-xs leading-relaxed text-slate-600 dark:text-muted-foreground">
              <span className="mt-1.5 size-1.5 shrink-0 rounded-full" style={{ backgroundColor: TONE_COLOUR[s.tone] }} />
              {s.text}
            </li>
          ))}
        </ul>
        <p className="mt-3 border-t border-slate-100 pt-2 text-[10px] text-slate-400 dark:border-border">
          Checked {formatWhen(data.computedAt)} · {hero.rulesActive} rules in {(data.runDurationMs / 1000).toFixed(1)} s
        </p>
      </Card>
    </div>
  );
}

function DeltaIcon({ delta }: { delta: number | null }) {
  if (delta == null || Math.abs(delta) < 0.05) return <Minus className="size-3.5 text-slate-400" />;
  return delta > 0 ? (
    <ArrowUpRight className="size-3.5 text-[#0f8f7e]" />
  ) : (
    <ArrowDownRight className="size-3.5 text-[#d69e2e]" />
  );
}

function KpiTile({
  icon,
  label,
  value,
  foot,
  accent,
  spark,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  foot: string;
  accent: string;
  spark?: Array<number | null>;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(cardClass, "group p-3.5 text-left transition hover:border-[#8fb3f5] hover:shadow-md")}
    >
      <div className="flex items-center gap-2 text-2xs font-medium uppercase tracking-wide text-slate-500">
        <span className="icon-well size-6 rounded-md" style={{ backgroundColor: `${accent}17`, color: accent }}>
          {icon}
        </span>
        <span className="truncate">{label}</span>
      </div>
      <div className="mt-2 flex items-end justify-between gap-2">
        <p className="truncate text-2xl font-semibold tracking-tight text-slate-900 tabular-nums dark:text-foreground">
          {value}
        </p>
        {spark ? <Sparkline values={spark} colour={accent} width={64} height={24} /> : null}
      </div>
      <p className="mt-0.5 truncate text-2xs text-slate-400">{foot}</p>
    </button>
  );
}
