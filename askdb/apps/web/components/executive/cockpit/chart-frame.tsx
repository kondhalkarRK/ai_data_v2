"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Download, Maximize2, Minimize2 } from "lucide-react";
import * as React from "react";
import { createPortal } from "react-dom";

import { exportCsv, exportSvgPng } from "@/components/executive/cockpit/chart-utils";
import { cn } from "@/lib/utils";

export function ChartFrame({
  title,
  subtitle,
  controls,
  csv,
  png = true,
  exportName,
  className,
  bodyClassName,
  children,
}: {
  title: string;
  subtitle?: React.ReactNode;
  controls?: React.ReactNode;
  csv?: () => Array<Record<string, unknown>>;
  /** Offer PNG export; needs an `svg[data-chart]` in the body. */
  png?: boolean;
  exportName: string;
  className?: string;
  bodyClassName?: string;
  children: (expanded: boolean) => React.ReactNode;
}) {
  const [expanded, setExpanded] = React.useState(false);
  const bodyRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!expanded) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setExpanded(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded]);

  const exportPng = async () => {
    const svg = bodyRef.current?.querySelector("svg[data-chart]") as SVGSVGElement | null;
    if (svg) await exportSvgPng(svg, `${exportName}.png`);
  };

  const card = (
    <section
      className={cn(
        "flex min-w-0 flex-col rounded-2xl border border-slate-200/70 bg-white/90 p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_8px_24px_-12px_rgba(15,23,42,0.08)] dark:border-border dark:bg-surface-raised",
        expanded && "h-full w-full bg-white dark:bg-surface-raised",
        !expanded && className,
      )}
    >
      <header className="mb-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold tracking-tight text-slate-800 dark:text-foreground">
            {title}
          </h3>
          {subtitle ? (
            <p className="mt-0.5 truncate text-2xs text-slate-500 dark:text-muted-foreground">{subtitle}</p>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {controls}
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <button
                type="button"
                aria-label={`Export ${title}`}
                className="rounded-md p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-muted"
              >
                <Download className="size-3.5" />
              </button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content
                align="end"
                sideOffset={4}
                className="z-[70] min-w-36 rounded-lg border border-slate-200 bg-white p-1 text-xs shadow-lg dark:border-border dark:bg-surface-raised"
              >
                {png ? (
                  <DropdownMenu.Item
                    className="cursor-pointer rounded px-2 py-1.5 outline-none data-[highlighted]:bg-slate-100 dark:data-[highlighted]:bg-muted"
                    onSelect={() => void exportPng()}
                  >
                    Download PNG
                  </DropdownMenu.Item>
                ) : null}
                {csv ? (
                  <DropdownMenu.Item
                    className="cursor-pointer rounded px-2 py-1.5 outline-none data-[highlighted]:bg-slate-100 dark:data-[highlighted]:bg-muted"
                    onSelect={() => exportCsv(csv(), `${exportName}.csv`)}
                  >
                    Download CSV
                  </DropdownMenu.Item>
                ) : null}
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
          <button
            type="button"
            aria-label={expanded ? "Exit full screen" : `Full screen ${title}`}
            className="rounded-md p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-muted"
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}
          </button>
        </div>
      </header>
      <div ref={bodyRef} className={cn("relative min-h-0 flex-1", bodyClassName)}>
        {children(expanded)}
      </div>
    </section>
  );

  if (!expanded) return card;
  return (
    <>
      <div className={cn("invisible", className)} aria-hidden="true" />
      {createPortal(
        <div
          className="fixed inset-0 z-[60] flex bg-slate-900/25 p-4 backdrop-blur-sm sm:p-8"
          role="dialog"
          aria-modal="true"
          aria-label={title}
          onClick={(event) => {
            if (event.target === event.currentTarget) setExpanded(false);
          }}
        >
          {card}
        </div>,
        document.body,
      )}
    </>
  );
}

/** Small segmented toggle used in chart headers. */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
}) {
  return (
    <div className="mr-1 inline-flex rounded-lg bg-slate-100 p-0.5 text-2xs dark:bg-muted">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={cn(
            "rounded-md px-2 py-0.5 font-medium transition",
            value === option.value
              ? "bg-white text-slate-800 shadow-sm dark:bg-surface-raised dark:text-foreground"
              : "text-slate-500 hover:text-slate-700",
          )}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

/** Floating tooltip positioned inside a relative container. */
export function ChartTooltip({
  x,
  y,
  width,
  children,
}: {
  x: number;
  y: number;
  width: number;
  children: React.ReactNode;
}) {
  const flip = x > width * 0.6;
  return (
    <div
      className="pointer-events-none absolute z-10 min-w-40 rounded-lg border border-slate-200 bg-white/95 px-3 py-2 text-2xs shadow-lg backdrop-blur dark:border-border dark:bg-surface-raised/95"
      style={{
        left: flip ? undefined : x + 14,
        right: flip ? width - x + 14 : undefined,
        top: Math.max(0, y - 10),
      }}
    >
      {children}
    </div>
  );
}
