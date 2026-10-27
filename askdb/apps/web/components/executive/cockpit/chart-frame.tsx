"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Download, Maximize2, Minimize2 } from "lucide-react";
import * as React from "react";
import { createPortal } from "react-dom";

import { exportCsv, exportSvgPng } from "@/components/executive/cockpit/chart-utils";
import { interactive, overlay, surface, type as typeScale } from "@/lib/surface";
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
        "flex min-w-0 flex-col p-5",
        surface.panelElevated,
        "rounded-2xl",
        expanded && "h-full w-full bg-surface-raised",
        !expanded && className,
      )}
    >
      <header className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className={cn("truncate text-[15px]", typeScale.title)}>{title}</h3>
          {subtitle ? <p className={cn("mt-1 truncate", typeScale.subtitle)}>{subtitle}</p> : null}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {controls}
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <button
                type="button"
                aria-label={`Export ${title}`}
                className={interactive.iconGhost}
              >
                <Download className="size-3.5" />
              </button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content
                align="end"
                sideOffset={4}
                className={overlay.dropdown}
              >
                {png ? (
                  <DropdownMenu.Item
                    className={overlay.menuItem}
                    onSelect={() => void exportPng()}
                  >
                    Download PNG
                  </DropdownMenu.Item>
                ) : null}
                {csv ? (
                  <DropdownMenu.Item
                    className={overlay.menuItem}
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
            className={interactive.iconGhost}
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
          className={cn("fixed inset-0 z-[60] flex p-4 sm:p-8", overlay.scrim)}
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
    <div className="segmented-control mr-1">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          data-active={value === option.value ? "true" : "false"}
          className="rounded-md px-2 py-0.5 font-medium transition"
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
      className={cn("absolute z-10 min-w-40", overlay.tooltip)}
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
