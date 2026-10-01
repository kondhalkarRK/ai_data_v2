"use client";

import type * as React from "react";

import { COCKPIT } from "@/components/executive/cockpit/palette";
import type { Band, DimensionKey, RuleStatus, Severity, Tone } from "@/components/reliability/types";
import { cn } from "@/lib/utils";

/** Trust palette: soft blue, teal, trust green and executive grey; coral only for real risk. */
export const TRUST = {
  ...COCKPIT,
  green: "#0f8f7e",
  greenMist: "#dcf3ee",
  coral: "#c8574d",
  coralMist: "#fbecea",
  amberInk: "#94660f",
} as const;

export const BAND_COLOUR: Record<Band, string> = {
  excellent: TRUST.green,
  good: TRUST.teal,
  fair: TRUST.amber,
  risk: TRUST.coral,
  unknown: TRUST.greySoft,
};

export const DIMENSION_COLOUR: Record<DimensionKey, string> = {
  accuracy: "#2f6fed",
  completeness: "#14a3a1",
  consistency: "#5b8def",
  timeliness: "#0e7c86",
  validity: "#7c9cc9",
  uniqueness: "#3fbfb5",
};

export const DIMENSION_LABEL: Record<DimensionKey, string> = {
  accuracy: "Accuracy",
  completeness: "Completeness",
  consistency: "Consistency",
  timeliness: "Timeliness",
  validity: "Validity",
  uniqueness: "Uniqueness",
};

export const SEVERITIES: Severity[] = ["critical", "high", "medium", "low"];

const SEVERITY_STYLE: Record<Severity, string> = {
  critical: "bg-[#fbecea] text-[#a8463d] ring-[#f1cfca]",
  high: "bg-[#fdf3dc] text-[#94660f] ring-[#f0dfb4]",
  medium: "bg-[#e3ecfd] text-[#2f5fc4] ring-[#c9dafb]",
  low: "bg-slate-100 text-slate-600 ring-slate-200",
};

export const SEVERITY_DOT: Record<Severity, string> = {
  critical: TRUST.coral,
  high: TRUST.amber,
  medium: TRUST.blue,
  low: TRUST.greySoft,
};

export function SeverityChip({ severity, className }: { severity: Severity; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-2xs font-medium capitalize ring-1 ring-inset",
        SEVERITY_STYLE[severity],
        className,
      )}
    >
      {severity}
    </span>
  );
}

const STATUS_STYLE: Record<RuleStatus, { label: string; dot: string; text: string }> = {
  passing: { label: "Passing", dot: TRUST.green, text: "text-[#0f7a6c]" },
  failing: { label: "Failing", dot: TRUST.coral, text: "text-[#a8463d]" },
  error: { label: "Not run", dot: TRUST.amber, text: "text-[#94660f]" },
  no_data: { label: "No data", dot: TRUST.greySoft, text: "text-slate-500" },
  disabled: { label: "Disabled", dot: "#e2e8f0", text: "text-slate-400" },
};

export function StatusPill({ status }: { status: RuleStatus }) {
  const style = STATUS_STYLE[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-2xs font-medium", style.text)}>
      <span className="size-1.5 rounded-full" style={{ backgroundColor: style.dot }} />
      {style.label}
    </span>
  );
}

export const TONE_COLOUR: Record<Tone, string> = {
  positive: TRUST.green,
  info: TRUST.blue,
  warning: TRUST.amber,
  risk: TRUST.coral,
};

export const cardClass =
  "rounded-2xl border border-slate-200/70 bg-white/90 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_8px_24px_-14px_rgba(15,23,42,0.1)] dark:border-border dark:bg-surface-raised";

export function Card({ className, children }: { className?: string; children: React.ReactNode }) {
  return <section className={cn(cardClass, "p-5", className)}>{children}</section>;
}

export function PanelTitle({
  title,
  subtitle,
  right,
}: {
  title: string;
  subtitle?: React.ReactNode;
  right?: React.ReactNode;
}) {
  return (
    <header className="mb-4 flex items-start justify-between gap-3">
      <div className="min-w-0">
        <h3 className="truncate text-[15px] font-semibold tracking-tight text-slate-800 dark:text-foreground">{title}</h3>
        {subtitle ? <p className="mt-1 text-xs text-slate-500 dark:text-muted-foreground">{subtitle}</p> : null}
      </div>
      {right ? <div className="flex shrink-0 items-center gap-1">{right}</div> : null}
    </header>
  );
}

export function formatScore(score: number | null | undefined, digits = 1): string {
  return score == null ? "—" : score.toFixed(digits);
}

export function formatDelta(delta: number | null | undefined): string {
  if (delta == null) return "—";
  if (Math.abs(delta) < 0.05) return "steady";
  return `${delta > 0 ? "+" : ""}${delta.toFixed(1)} pts`;
}

/** "3h ago" for recent timestamps, otherwise a short date. */
export function formatWhen(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "—";
  const date = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  if (Number.isNaN(date.getTime())) return iso;
  if (iso.length === 10) return date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  const minutes = Math.round((now.getTime() - date.getTime()) / 60_000);
  if (minutes >= 0 && minutes < 1) return "just now";
  if (minutes >= 0 && minutes < 60) return `${minutes}m ago`;
  if (minutes >= 0 && minutes < 60 * 24) return `${Math.round(minutes / 60)}h ago`;
  if (minutes >= 0 && minutes < 60 * 24 * 7) return `${Math.round(minutes / 1440)}d ago`;
  return date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export function formatHours(hours: number | null | undefined): string {
  if (hours == null) return "—";
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} min`;
  if (hours < 48) return `${hours.toFixed(hours < 10 ? 1 : 0)} h`;
  return `${(hours / 24).toFixed(hours < 240 ? 1 : 0)} days`;
}

/** Ring showing a 0–100 score, coloured by band. */
export function ScoreRing({
  score,
  band,
  size = 44,
  stroke = 4,
}: {
  score: number | null;
  band: Band;
  size?: number;
  stroke?: number;
}) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const filled = score == null ? 0 : Math.max(0, Math.min(100, score)) / 100;
  return (
    <svg width={size} height={size} className="shrink-0 -rotate-90" aria-hidden="true">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#eef2f7" strokeWidth={stroke} />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={BAND_COLOUR[band]}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={`${c * filled} ${c}`}
      />
    </svg>
  );
}

export function Sparkline({
  values,
  colour,
  width = 88,
  height = 26,
}: {
  values: Array<number | null>;
  colour: string;
  width?: number;
  height?: number;
}) {
  const clean = values.filter((v): v is number => v != null);
  if (clean.length < 2) return <span className="text-2xs text-slate-300">—</span>;
  const max = Math.max(...clean);
  const min = Math.min(...clean);
  const span = max - min || 1;
  const pts = clean.map((v, i) => {
    const x = (i / (clean.length - 1)) * width;
    const y = height - 3 - ((v - min) / span) * (height - 6);
    return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return (
    <svg width={width} height={height} className="shrink-0" aria-hidden="true">
      <path d={pts.join(" ")} fill="none" stroke={colour} strokeWidth={1.5} strokeLinejoin="round" />
    </svg>
  );
}

export function EmptyNote({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-xl border border-dashed border-slate-200 bg-slate-50/60 px-3 py-4 text-center text-2xs text-slate-500">
      {children}
    </p>
  );
}
