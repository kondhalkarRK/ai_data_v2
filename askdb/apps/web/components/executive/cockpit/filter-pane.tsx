"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ChevronRight, RotateCcw, SlidersHorizontal, X } from "lucide-react";
import * as React from "react";

import type { CockpitFilters, CockpitOptions, FilterKey, OptionItem } from "@/components/executive/cockpit/types";
import { cn } from "@/lib/utils";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function activeFilterCount(filters: CockpitFilters): number {
  return Object.values(filters).filter(Boolean).length;
}

export function FilterPane({
  open,
  onOpenChange,
  filters,
  options,
  onChange,
  onClear,
  hideGeography = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  filters: CockpitFilters;
  options: CockpitOptions | undefined;
  onChange: (next: CockpitFilters) => void;
  onClear: () => void;
  hideGeography?: boolean;
}) {
  const count = activeFilterCount(filters);

  React.useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onOpenChange(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  const set = (key: FilterKey, value: string) => {
    const next: CockpitFilters = { ...filters, [key]: value || undefined };
    if (key === "month" && value) next.quarter = undefined;
    if (key === "quarter" && value) next.month = undefined;
    if (key === "make") {
      const stillValid = options?.models.some((m) => m.value === next.model && (!value || m.group === value));
      if (!stillValid) next.model = undefined;
    }
    if (key === "zone" && value) {
      const state = options?.states.find((s) => s.value === next.state);
      if (state && state.group !== value) next.state = undefined;
    }
    if (key === "dealer_id") next.sales_person_id = undefined;
    onChange(next);
  };

  const models = options?.models.filter((m) => !filters.make || m.group === filters.make) ?? [];
  const states = options?.states.filter((s) => !filters.zone || s.group === filters.zone) ?? [];

  return (
    <>
      <AnimatePresence>
        {!open ? (
          <motion.button
            key="tab"
            type="button"
            initial={{ x: 40, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 40, opacity: 0 }}
            onClick={() => onOpenChange(true)}
            className="fixed right-0 top-1/2 z-40 flex -translate-y-1/2 flex-col items-center gap-2 rounded-l-xl border border-r-0 border-slate-200 bg-white/95 px-2 py-3 text-2xs font-semibold text-slate-600 shadow-lg backdrop-blur hover:text-[#2f6fed] dark:border-border dark:bg-surface-raised"
            aria-label="Open filters"
          >
            <SlidersHorizontal className="size-4" />
            <span className="[writing-mode:vertical-rl]">Filters</span>
            {count ? (
              <span className="grid size-5 place-items-center rounded-full bg-[#2f6fed] text-[10px] text-white">{count}</span>
            ) : null}
          </motion.button>
        ) : null}
      </AnimatePresence>
      <AnimatePresence>
        {open ? (
          <motion.aside
            key="pane"
            initial={{ x: 360, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 360, opacity: 0 }}
            transition={{ type: "spring", stiffness: 380, damping: 36 }}
            className="fixed bottom-4 right-4 top-20 z-50 flex w-[19rem] flex-col rounded-2xl border border-slate-200 bg-white/95 shadow-[0_24px_48px_-16px_rgba(15,23,42,0.25)] backdrop-blur-md dark:border-border dark:bg-surface-raised/95"
            aria-label="Dashboard filters"
          >
            <header className="flex items-center justify-between border-b border-slate-100 px-4 py-3 dark:border-border">
              <div className="flex items-center gap-2">
                <SlidersHorizontal className="size-4 text-[#2f6fed]" />
                <h2 className="text-sm font-semibold text-slate-800 dark:text-foreground">Filters</h2>
                {count ? (
                  <span className="rounded-full bg-[#e3ecfd] px-1.5 py-0.5 text-[10px] font-semibold text-[#2f6fed]">
                    {count} active
                  </span>
                ) : null}
              </div>
              <button
                type="button"
                onClick={() => onOpenChange(false)}
                className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-muted"
                aria-label="Collapse filters"
              >
                <ChevronRight className="size-4" />
              </button>
            </header>
            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-3">
              <Group title="Time">
                <Select
                  label="Year"
                  value={filters.year}
                  onChange={(v) => set("year", v)}
                  placeholder="Latest year"
                  options={(options?.years ?? []).map((y) => ({ value: String(y), label: String(y), group: null }))}
                />
                <div className="grid grid-cols-2 gap-2">
                  <Select
                    label="Quarter"
                    value={filters.quarter}
                    onChange={(v) => set("quarter", v)}
                    placeholder="All"
                    options={[1, 2, 3, 4].map((q) => ({ value: String(q), label: `Q${q}`, group: null }))}
                  />
                  <Select
                    label="Month"
                    value={filters.month}
                    onChange={(v) => set("month", v)}
                    placeholder="All"
                    options={MONTHS.map((m, i) => ({ value: String(i + 1), label: m, group: null }))}
                  />
                </div>
              </Group>
              <Group title="Product">
                <Select label="Make" value={filters.make} onChange={(v) => set("make", v)} options={options?.makes ?? []} />
                <Select
                  label="Model"
                  value={filters.model}
                  onChange={(v) => set("model", v)}
                  options={models}
                  grouped={!filters.make}
                />
                <Select
                  label="Fuel type"
                  value={filters.engine_type}
                  onChange={(v) => set("engine_type", v)}
                  options={options?.engineTypes ?? []}
                />
                <Select
                  label="Vehicle type"
                  value={filters.car_type}
                  onChange={(v) => set("car_type", v)}
                  options={options?.carTypes ?? []}
                  grouped
                />
              </Group>
              <Group title="Geography & channel">
                {hideGeography ? (
                  <p className="px-0.5 text-[11px] text-muted-foreground">
                    Region is set by your login and cannot be changed.
                  </p>
                ) : (
                  <Select label="Region" value={filters.zone} onChange={(v) => set("zone", v)} options={options?.zones ?? []} />
                )}
                {hideGeography ? null : (
                <Select
                  label="State"
                  value={filters.state}
                  onChange={(v) => set("state", v)}
                  options={states}
                  grouped={!filters.zone}
                />
                )}
                {hideGeography || !filters.city ? null : (
                  <div className="flex items-center justify-between rounded-lg bg-slate-50 px-2.5 py-1.5 text-xs dark:bg-muted">
                    <span>
                      <span className="text-slate-500">City</span>{" "}
                      <span className="font-medium text-slate-800 dark:text-foreground">{filters.city}</span>
                    </span>
                    <button type="button" aria-label="Clear city" onClick={() => set("city", "")}>
                      <X className="size-3.5 text-slate-400 hover:text-slate-700" />
                    </button>
                  </div>
                )}
                <Select
                  label="Dealer"
                  value={filters.dealer_id}
                  onChange={(v) => set("dealer_id", v)}
                  options={options?.dealers ?? []}
                />
                <Select
                  label="Salesperson"
                  value={filters.sales_person_id}
                  onChange={(v) => set("sales_person_id", v)}
                  options={options?.salespeople ?? []}
                  disabled={!filters.dealer_id}
                  placeholder={filters.dealer_id ? "All" : "Choose a dealer first"}
                />
              </Group>
            </div>
            <footer className="flex items-center justify-between border-t border-slate-100 px-4 py-3 dark:border-border">
              <button
                type="button"
                onClick={onClear}
                disabled={!count}
                className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-800 disabled:opacity-40"
              >
                <RotateCcw className="size-3.5" /> Clear all
              </button>
              <button
                type="button"
                onClick={() => onOpenChange(false)}
                className="rounded-lg bg-[#2f6fed] px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-[#245fd6]"
              >
                Done
              </button>
            </footer>
          </motion.aside>
        ) : null}
      </AnimatePresence>
    </>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <fieldset className="space-y-2">
      <legend className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">{title}</legend>
      {children}
    </fieldset>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
  placeholder = "All",
  grouped = false,
  disabled = false,
}: {
  label: string;
  value: string | undefined;
  onChange: (value: string) => void;
  options: OptionItem[];
  placeholder?: string;
  grouped?: boolean;
  disabled?: boolean;
}) {
  const id = React.useId();
  const groups = React.useMemo(() => {
    if (!grouped) return null;
    const map = new Map<string, OptionItem[]>();
    for (const option of options) {
      const key = option.group ?? "Other";
      map.set(key, [...(map.get(key) ?? []), option]);
    }
    return [...map.entries()];
  }, [grouped, options]);
  return (
    <label htmlFor={id} className="block">
      <span className="mb-1 block text-2xs font-medium text-slate-500">{label}</span>
      <select
        id={id}
        value={value ?? ""}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className={cn(
          "h-8 w-full rounded-lg border bg-white px-2 text-xs text-slate-800 outline-none transition focus:border-[#8fb3f5] focus:ring-2 focus:ring-[#e3ecfd] disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400 dark:bg-surface-raised dark:text-foreground",
          value ? "border-[#8fb3f5]" : "border-slate-200 dark:border-border",
        )}
      >
        <option value="">{placeholder}</option>
        {groups
          ? groups.map(([group, items]) => (
              <optgroup key={group} label={group}>
                {items.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </optgroup>
            ))
          : options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
      </select>
    </label>
  );
}
