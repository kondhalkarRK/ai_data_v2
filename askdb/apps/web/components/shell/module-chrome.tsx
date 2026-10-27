"use client";

import type * as React from "react";
import { X } from "lucide-react";

import { cn } from "@/lib/utils";

/** Shared page chrome for Executive, Data Trust, Chat, and Analytics Builder. */
export function ModuleWorkspace({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={cn("space-y-6", className)}>{children}</div>;
}

export function ModulePageHeader({
  eyebrow,
  title,
  meta,
  actions,
}: {
  eyebrow: string;
  title: React.ReactNode;
  meta?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-primary">{eyebrow}</p>
        <h1 className="mt-0.5 text-xl font-semibold tracking-tight text-foreground">{title}</h1>
        {meta ? <div className="mt-0.5 text-sm text-muted-foreground">{meta}</div> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function ModuleSection({
  title,
  description,
  children,
  id,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  id?: string;
}) {
  return (
    <section id={id} className="scroll-mt-4 space-y-5">
      <div className="border-b border-border pb-3">
        <h2 className="text-base font-semibold tracking-tight text-foreground">{title}</h2>
        {description ? <p className="mt-0.5 text-xs text-muted-foreground">{description}</p> : null}
      </div>
      <div className="space-y-6">{children}</div>
    </section>
  );
}

export function ModuleToolbarButton({
  children,
  onClick,
  active = false,
  primary = false,
  disabled = false,
  type = "button",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  active?: boolean;
  primary?: boolean;
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "inline-flex h-8 items-center gap-1.5 rounded-lg border px-3 text-xs font-medium transition disabled:opacity-50",
        primary
          ? "border-primary/40 bg-primary text-primary-foreground shadow-sm hover:bg-primary/90"
          : active
            ? "border-primary/35 bg-primary/10 text-primary"
            : "border-border bg-surface-raised text-foreground hover:bg-muted",
      )}
    >
      {children}
    </button>
  );
}

export function ModuleFilterChips({
  chips,
  onRemove,
  onClear,
}: {
  chips: Array<{ key: string; label: string; value: string }>;
  onRemove: (key: string) => void;
  onClear: () => void;
}) {
  if (!chips.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {chips.map((chip) => (
        <span
          key={chip.key}
          className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/8 py-0.5 pl-2.5 pr-1 text-2xs text-foreground"
        >
          <span className="text-muted-foreground">{chip.label}:</span>
          <span className="font-semibold">{chip.value}</span>
          <button
            type="button"
            aria-label={`Remove ${chip.label} filter`}
            className="rounded-full p-0.5 hover:bg-muted"
            onClick={() => onRemove(chip.key)}
          >
            <X className="size-3" />
          </button>
        </span>
      ))}
      <button type="button" className="ml-1 text-2xs font-medium text-primary hover:underline" onClick={onClear}>
        Clear all
      </button>
    </div>
  );
}

export function ModuleStatusBanner({
  tone,
  children,
}: {
  tone: "ok" | "warn" | "info";
  children: React.ReactNode;
}) {
  return (
    <p
      role={tone === "warn" ? "alert" : "status"}
      className={cn(
        "rounded-xl border px-3 py-2 text-xs",
        tone === "ok" && "border-success/30 bg-success/8 text-foreground",
        tone === "warn" && "border-warning/35 bg-warning/10 text-warning-foreground dark:text-warning",
        tone === "info" && "border-border bg-muted/50 text-muted-foreground",
      )}
    >
      {children}
    </p>
  );
}

export function ModulePanel({
  children,
  className,
  padded = true,
}: {
  children: React.ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-2xl border border-border/70 bg-surface-raised shadow-[var(--shadow-card)]",
        padded && "p-4 sm:p-5",
        className,
      )}
    >
      {children}
    </div>
  );
}
