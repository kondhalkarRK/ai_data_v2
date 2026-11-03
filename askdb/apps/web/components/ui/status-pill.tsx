import {
  AlertTriangle,
  CheckCircle2,
  CircleAlert,
  Info,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import * as React from "react";

import { statusToneClasses, type StatusTone } from "@/lib/design";
import { cn } from "@/lib/utils";

const ICONS: Record<StatusTone, LucideIcon> = {
  ok: CheckCircle2,
  warn: AlertTriangle,
  fail: CircleAlert,
  info: Info,
  ai: Sparkles,
  neutral: Info,
};

/** Color + distinct icon shape (accessibility — never color alone). */
export function StatusPill({
  tone,
  label,
  className,
}: {
  tone: StatusTone;
  label: string;
  className?: string;
}) {
  const Icon = ICONS[tone];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium",
        statusToneClasses(tone),
        className,
      )}
    >
      <Icon className="size-3 shrink-0" aria-hidden="true" />
      {label}
    </span>
  );
}

export function EmptyState({
  title,
  detail,
  action,
  className,
}: {
  title: string;
  detail?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "empty-state rounded-[var(--radius-card)] border border-dashed border-border/80 bg-surface/60 px-5 py-10 text-center",
        className,
      )}
    >
      <p className="text-sm font-medium text-foreground">{title}</p>
      {detail ? <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{detail}</p> : null}
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}
