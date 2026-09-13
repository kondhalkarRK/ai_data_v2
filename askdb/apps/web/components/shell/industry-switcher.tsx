"use client";

import type { Industry } from "@nql/shared-types";
import { Car, Check, ChevronDown, ShieldHalf } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { useActiveIndustry, useSetDefaultIndustry } from "@/hooks/use-session";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui-store";

const INDUSTRIES = [
  { value: "insurance", label: "Insurance", icon: ShieldHalf },
  { value: "automotive", label: "Automotive", icon: Car },
] as const satisfies ReadonlyArray<{ value: Industry; label: string; icon: typeof Car }>;

/**
 * Switches the analytics database backing the whole workspace.
 *
 * Changing industry swaps the semantic model, the KPI set and the target database. The
 * override is applied locally first so the UI reacts immediately, then persisted as the
 * user's default in the background.
 */
export function IndustrySwitcher() {
  const active = useActiveIndustry();
  const setIndustryOverride = useUiStore((state) => state.setIndustryOverride);
  const setDefault = useSetDefaultIndustry();

  const [open, setOpen] = React.useState(false);
  const containerRef = React.useRef<HTMLDivElement>(null);

  // Close on an outside click or Escape, the two things a user expects from a menu.
  React.useEffect(() => {
    if (!open) return;

    function onPointerDown(event: PointerEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const current = INDUSTRIES.find((item) => item.value === active) ?? INDUSTRIES[0];
  const CurrentIcon = current.icon;

  function select(industry: Industry) {
    setOpen(false);
    if (industry === active) return;
    setIndustryOverride(industry);
    setDefault.mutate(industry);
  }

  return (
    <div ref={containerRef} className="relative">
      <Button
        variant="secondary"
        size="sm"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Active domain: ${current.label}. Domain is admin-configured, not auto-detected.`}
        title="Domain is an explicit configuration (not inferred from data)."
        onClick={() => setOpen((value) => !value)}
      >
        <CurrentIcon />
        <span className="hidden sm:inline">{current.label}</span>
        <ChevronDown className={cn("transition-transform", open && "rotate-180")} />
      </Button>

      {open ? (
        <ul
          role="listbox"
          aria-label="Industry"
          className="absolute right-0 z-30 mt-1.5 w-52 overflow-hidden rounded-[var(--radius-card)] border border-border bg-popover p-1 shadow-[var(--shadow-overlay)]"
        >
          {INDUSTRIES.map(({ value, label, icon: Icon }) => {
            const selected = value === active;
            return (
              <li key={value}>
                <button
                  type="button"
                  role="option"
                  aria-selected={selected}
                  onClick={() => select(value)}
                  className={cn(
                    "flex w-full items-center gap-2.5 rounded-[var(--radius-control)] px-2.5 py-2 text-left text-sm transition-colors",
                    selected
                      ? "bg-primary/10 text-primary"
                      : "text-foreground hover:bg-muted",
                  )}
                >
                  <Icon className="size-4 shrink-0" aria-hidden="true" />
                  <span className="flex-1">{label}</span>
                  {selected ? <Check className="size-4" aria-hidden="true" /> : null}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
