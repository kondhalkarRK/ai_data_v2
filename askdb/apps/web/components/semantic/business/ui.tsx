"use client";

import { MessageSquareText, type LucideIcon } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

import type { ExampleQuestion } from "./semantic-layer";

export const panelClass = "rounded-2xl border border-border/70 bg-surface-raised/80 shadow-sm";

export function BlockHeader({ title, description }: { title: string; description: string }) {
  return (
    <div className="border-b border-border/60 pb-3">
      <h3 className="text-base font-semibold tracking-tight text-foreground">{title}</h3>
      <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
    </div>
  );
}

const TONES = {
  neutral: "bg-muted/60 text-muted-foreground",
  primary: "bg-primary/12 text-primary",
  info: "bg-info/15 text-info",
  success: "bg-success/15 text-success",
  warning: "bg-warning/15 text-warning",
  danger: "bg-danger/12 text-danger",
} as const;

export type Tone = keyof typeof TONES;

export function Chip({ children, tone = "neutral", className }: { children: ReactNode; tone?: Tone; className?: string }) {
  return (
    <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium", TONES[tone], className)}>
      {children}
    </span>
  );
}

export function FieldLabel({ children }: { children: ReactNode }) {
  return (
    <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{children}</p>
  );
}

export function ExampleQuestions({ items }: { items: ExampleQuestion[] }) {
  if (!items.length) return <span className="text-xs text-muted-foreground/80">No examples yet</span>;
  return (
    <ul className="space-y-1.5">
      {items.map((item) => (
        <li key={item.text}>
          <Link
            href={`/chat?q=${encodeURIComponent(item.text)}`}
            className="group flex items-start gap-2 rounded-lg border border-border/50 bg-background/50 px-2.5 py-1.5 text-xs text-foreground transition-colors hover:border-primary/40 hover:bg-primary/5"
            title="Ask this in AI Chat"
          >
            <MessageSquareText className="mt-0.5 size-3.5 shrink-0 text-primary/80" />
            <span className="flex-1">{item.text}</span>
            <span className="shrink-0 text-[10px] text-muted-foreground">{item.curated ? "Curated" : "Suggested"}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function SegmentedTabs<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
  size = "sm",
}: {
  value: T;
  options: Array<{ value: T; label: ReactNode; icon?: LucideIcon }>;
  onChange: (value: T) => void;
  ariaLabel: string;
  size?: "sm" | "md";
}) {
  return (
    <div role="tablist" aria-label={ariaLabel} className="inline-flex flex-wrap gap-0.5 rounded-xl bg-muted/50 p-1">
      {options.map((option) => {
        const active = option.value === value;
        const Icon = option.icon;
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={active}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-lg font-medium transition-colors",
              size === "md" ? "px-3.5 py-1.5 text-sm" : "px-2.5 py-1 text-xs",
              active
                ? "bg-surface-raised text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
            onClick={() => onChange(option.value)}
          >
            {Icon ? <Icon className="size-3.5" /> : null}
            {option.label}
          </button>
        );
      })}
    </div>
  );
}