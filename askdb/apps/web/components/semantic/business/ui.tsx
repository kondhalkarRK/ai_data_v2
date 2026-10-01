"use client";

import { ChevronDown, MessageSquareText, type LucideIcon } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

import type { ExampleQuestion } from "./semantic-layer";

export const panelClass = "rounded-2xl border border-border/70 bg-surface-raised/80 shadow-sm";

export function Section({
  id,
  icon: Icon,
  title,
  description,
  count,
  open,
  onToggle,
  actions,
  children,
}: {
  id: string;
  icon: LucideIcon;
  title: string;
  description: string;
  count?: ReactNode;
  open: boolean;
  onToggle: () => void;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section id={id} className={cn(panelClass, "scroll-mt-24")}>
      <div className="flex flex-wrap items-center gap-3 px-4 py-3.5 sm:px-5">
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
          aria-expanded={open}
          aria-controls={`${id}-body`}
          onClick={onToggle}
        >
          <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Icon className="size-4" />
          </span>
          <span className="min-w-0">
            <span className="flex items-center gap-2">
              <span className="text-[15px] font-semibold text-foreground">{title}</span>
              {count !== undefined ? (
                <span className="rounded-full bg-muted/60 px-2 py-0.5 text-[11px] font-medium tabular-nums text-muted-foreground">
                  {count}
                </span>
              ) : null}
            </span>
            <span className="mt-0.5 block text-xs text-muted-foreground">{description}</span>
          </span>
          <ChevronDown
            className={cn("ml-auto size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
          />
        </button>
        {open && actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
      {open ? (
        <div id={`${id}-body`} className="border-t border-border/60 px-4 pb-4 pt-3 sm:px-5">
          {children}
        </div>
      ) : null}
    </section>
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

export function ChipList({ items, empty = "None recorded", max }: { items: string[]; empty?: string; max?: number }) {
  if (!items.length) return <span className="text-xs text-muted-foreground/80">{empty}</span>;
  const shown = max ? items.slice(0, max) : items;
  return (
    <span className="flex flex-wrap gap-1">
      {shown.map((item) => (
        <Chip key={item}>{item}</Chip>
      ))}
      {max && items.length > max ? <Chip tone="primary">+{items.length - max}</Chip> : null}
    </span>
  );
}

export function FieldLabel({ children }: { children: ReactNode }) {
  return (
    <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{children}</p>
  );
}

export function Field({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={className}>
      <FieldLabel>{label}</FieldLabel>
      <div className="text-sm text-foreground">{children}</div>
    </div>
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

export function ExpandButton({ open, label }: { open: boolean; label: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-primary" aria-hidden="true">
      {open ? "Hide" : label}
      <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} />
    </span>
  );
}
