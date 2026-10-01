"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Loader2, X } from "lucide-react";
import * as React from "react";

import { fieldClass } from "@/components/reliability/drilldown-panel";
import type { DimensionKey, MonitorCatalog, Severity } from "@/components/reliability/types";
import { DIMENSION_LABEL, SEVERITIES } from "@/components/reliability/ui";
import { cn } from "@/lib/utils";

export type MonitorKind = "not_null" | "unique" | "range" | "allowed_values" | "pattern" | "freshness" | "reference";

export interface CreateMonitorBody {
  name: string;
  description?: string;
  dimension: DimensionKey;
  dataset: string;
  severity: Severity;
  kind: MonitorKind;
  column?: string;
  columns?: string[];
  minValue?: number;
  maxValue?: number;
  allowed?: string[];
  pattern?: string;
  maxAgeHours?: number;
  refDataset?: string;
  refColumn?: string;
  threshold: number;
  owner: string;
  tags: string[];
}

const KINDS: Array<{ value: MonitorKind; label: string; hint: string; dimension: DimensionKey }> = [
  { value: "not_null", label: "Required values", hint: "Flags records where the column is empty.", dimension: "completeness" },
  { value: "unique", label: "No duplicates", hint: "Flags records sharing the same key.", dimension: "uniqueness" },
  { value: "range", label: "Value range", hint: "Flags values below a minimum or above a maximum.", dimension: "validity" },
  { value: "allowed_values", label: "Allowed values", hint: "Flags values outside an approved list.", dimension: "validity" },
  { value: "pattern", label: "Format (pattern)", hint: "Flags values not matching a regular expression.", dimension: "validity" },
  { value: "freshness", label: "Freshness", hint: "Flags when the newest record is older than allowed.", dimension: "timeliness" },
  { value: "reference", label: "Reference match", hint: "Flags values missing from another dataset.", dimension: "consistency" },
];

export function MonitorDialog({
  open,
  catalog,
  pending,
  error,
  onClose,
  onSubmit,
}: {
  open: boolean;
  catalog: MonitorCatalog;
  pending: boolean;
  error: string | null;
  onClose: () => void;
  onSubmit: (body: CreateMonitorBody) => void;
}) {
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [kind, setKind] = React.useState<MonitorKind>("not_null");
  const [dimension, setDimension] = React.useState<DimensionKey>("completeness");
  const [dimensionTouched, setDimensionTouched] = React.useState(false);
  const [dataset, setDataset] = React.useState(catalog.datasets[0]?.name ?? "");
  const [column, setColumn] = React.useState("");
  const [minValue, setMinValue] = React.useState("");
  const [maxValue, setMaxValue] = React.useState("");
  const [allowed, setAllowed] = React.useState("");
  const [pattern, setPattern] = React.useState("");
  const [maxAge, setMaxAge] = React.useState("36");
  const [refDataset, setRefDataset] = React.useState("");
  const [refColumn, setRefColumn] = React.useState("");
  const [severity, setSeverity] = React.useState<Severity>("medium");
  const [threshold, setThreshold] = React.useState("100");
  const [owner, setOwner] = React.useState(catalog.owners[0] ?? "Data Engineering");
  const [tags, setTags] = React.useState("");

  React.useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const columns = catalog.datasets.find((d) => d.name === dataset)?.columns ?? [];
  const refColumns = catalog.datasets.find((d) => d.name === refDataset)?.columns ?? [];
  const kindSpec = KINDS.find((k) => k.value === kind)!;

  const chooseKind = (next: MonitorKind) => {
    setKind(next);
    if (!dimensionTouched) setDimension(KINDS.find((k) => k.value === next)!.dimension);
  };

  const num = (v: string) => (v.trim() === "" ? undefined : Number(v));
  const thresholdValue = Number(threshold);
  const missing: string[] = [];
  if (name.trim().length < 3) missing.push("a name");
  if (!dataset) missing.push("a dataset");
  if (kind !== "freshness" && !column) missing.push("a column");
  if (kind === "range" && num(minValue) == null && num(maxValue) == null) missing.push("a minimum or maximum");
  if (kind === "allowed_values" && !allowed.trim()) missing.push("allowed values");
  if (kind === "pattern" && !pattern.trim()) missing.push("a pattern");
  if (kind === "freshness" && !(Number(maxAge) > 0)) missing.push("a maximum age");
  if (kind === "reference" && (!refDataset || !refColumn)) missing.push("a reference column");
  if (!Number.isFinite(thresholdValue) || thresholdValue < 0 || thresholdValue > 100) missing.push("a target between 0 and 100");

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (missing.length || pending) return;
    onSubmit({
      name: name.trim(),
      description: description.trim() || undefined,
      dimension,
      dataset,
      severity,
      kind,
      column: column || undefined,
      minValue: kind === "range" ? num(minValue) : undefined,
      maxValue: kind === "range" ? num(maxValue) : undefined,
      allowed:
        kind === "allowed_values"
          ? allowed
              .split(/[\n,]+/)
              .map((v) => v.trim())
              .filter(Boolean)
          : undefined,
      pattern: kind === "pattern" ? pattern : undefined,
      maxAgeHours: kind === "freshness" ? Number(maxAge) : undefined,
      refDataset: kind === "reference" ? refDataset : undefined,
      refColumn: kind === "reference" ? refColumn : undefined,
      threshold: thresholdValue,
      owner: owner.trim() || "Data Engineering",
      tags: tags
        .split(/[,\s]+/)
        .map((t) => t.trim())
        .filter(Boolean),
    });
  };

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="fixed inset-0 z-[60] flex items-start justify-center overflow-y-auto bg-slate-900/25 p-4 backdrop-blur-sm sm:p-10"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) onClose();
          }}
        >
          <motion.form
            role="dialog"
            aria-modal="true"
            aria-label="Create data quality monitor"
            onSubmit={submit}
            initial={{ y: 12, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 12, opacity: 0 }}
            className="w-full max-w-2xl rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-border dark:bg-surface-raised"
          >
            <header className="flex items-start justify-between border-b border-slate-100 px-5 py-4 dark:border-border">
              <div>
                <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-[#2f6fed]">New monitor</p>
                <h2 className="text-base font-semibold text-slate-900 dark:text-foreground">Create a data quality rule</h2>
                <p className="text-2xs text-slate-500">It runs with the next check and counts toward the trust score straight away.</p>
              </div>
              <button type="button" onClick={onClose} className="rounded-md p-1 text-slate-400 hover:bg-slate-100" aria-label="Close">
                <X className="size-4" />
              </button>
            </header>

            <div className="grid gap-4 px-5 py-4 sm:grid-cols-2">
              <Field label="Monitor name" className="sm:col-span-2">
                <input className={fieldClass} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Customer phone completeness" maxLength={120} />
              </Field>

              <Field label="What to check" className="sm:col-span-2">
                <div className="mt-1 grid grid-cols-2 gap-1.5 sm:grid-cols-4">
                  {KINDS.map((k) => (
                    <button
                      key={k.value}
                      type="button"
                      onClick={() => chooseKind(k.value)}
                      className={cn(
                        "rounded-lg border px-2 py-1.5 text-left text-2xs font-medium transition",
                        kind === k.value
                          ? "border-[#8fb3f5] bg-[#eef4ff] text-[#2f5fc4]"
                          : "border-slate-200 text-slate-600 hover:border-slate-300 dark:border-border",
                      )}
                    >
                      {k.label}
                    </button>
                  ))}
                </div>
                <p className="mt-1 text-[10px] text-slate-400">{kindSpec.hint}</p>
              </Field>

              <Field label="Dataset">
                <select
                  className={fieldClass}
                  value={dataset}
                  onChange={(e) => {
                    setDataset(e.target.value);
                    setColumn("");
                  }}
                >
                  {catalog.datasets.map((d) => (
                    <option key={d.name} value={d.name}>
                      {d.label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={kind === "freshness" ? "Date column (optional)" : "Column"}>
                <select className={fieldClass} value={column} onChange={(e) => setColumn(e.target.value)}>
                  <option value="">{kind === "freshness" ? "Dataset default" : "Choose column…"}</option>
                  {columns
                    .filter((c) => kind !== "freshness" || /date|time|unknown/i.test(c.type))
                    .map((c) => (
                      <option key={c.name} value={c.name}>
                        {c.label} ({c.type})
                      </option>
                    ))}
                </select>
              </Field>

              {kind === "range" ? (
                <>
                  <Field label="Minimum">
                    <input className={fieldClass} inputMode="decimal" value={minValue} onChange={(e) => setMinValue(e.target.value)} />
                  </Field>
                  <Field label="Maximum">
                    <input className={fieldClass} inputMode="decimal" value={maxValue} onChange={(e) => setMaxValue(e.target.value)} />
                  </Field>
                </>
              ) : null}
              {kind === "allowed_values" ? (
                <Field label="Allowed values (comma or new line separated)" className="sm:col-span-2">
                  <textarea className={cn(fieldClass, "h-16 py-1.5")} value={allowed} onChange={(e) => setAllowed(e.target.value)} />
                </Field>
              ) : null}
              {kind === "pattern" ? (
                <Field label="Regular expression" className="sm:col-span-2">
                  <input className={cn(fieldClass, "font-mono")} value={pattern} onChange={(e) => setPattern(e.target.value)} placeholder="^[A-Z]{2}[0-9]{2}$" />
                </Field>
              ) : null}
              {kind === "freshness" ? (
                <Field label="Maximum age (hours)">
                  <input className={fieldClass} inputMode="decimal" value={maxAge} onChange={(e) => setMaxAge(e.target.value)} />
                </Field>
              ) : null}
              {kind === "reference" ? (
                <>
                  <Field label="Reference dataset">
                    <select
                      className={fieldClass}
                      value={refDataset}
                      onChange={(e) => {
                        setRefDataset(e.target.value);
                        setRefColumn("");
                      }}
                    >
                      <option value="">Choose dataset…</option>
                      {catalog.datasets
                        .filter((d) => d.name !== dataset)
                        .map((d) => (
                          <option key={d.name} value={d.name}>
                            {d.label}
                          </option>
                        ))}
                    </select>
                  </Field>
                  <Field label="Reference column">
                    <select className={fieldClass} value={refColumn} onChange={(e) => setRefColumn(e.target.value)}>
                      <option value="">Choose column…</option>
                      {refColumns.map((c) => (
                        <option key={c.name} value={c.name}>
                          {c.label}
                        </option>
                      ))}
                    </select>
                  </Field>
                </>
              ) : null}

              <Field label="Dimension">
                <select
                  className={fieldClass}
                  value={dimension}
                  onChange={(e) => {
                    setDimension(e.target.value as DimensionKey);
                    setDimensionTouched(true);
                  }}
                >
                  {Object.entries(DIMENSION_LABEL).map(([k, label]) => (
                    <option key={k} value={k}>
                      {label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Severity">
                <select className={fieldClass} value={severity} onChange={(e) => setSeverity(e.target.value as Severity)}>
                  {SEVERITIES.map((s) => (
                    <option key={s} value={s}>
                      {s[0]!.toUpperCase() + s.slice(1)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Pass-rate target (%)">
                <input className={fieldClass} inputMode="decimal" value={threshold} onChange={(e) => setThreshold(e.target.value)} />
              </Field>
              <Field label="Owner">
                <input className={fieldClass} value={owner} onChange={(e) => setOwner(e.target.value)} list="dq-monitor-owners" />
                <datalist id="dq-monitor-owners">
                  {catalog.owners.map((o) => (
                    <option key={o} value={o} />
                  ))}
                </datalist>
              </Field>
              <Field label="Tags">
                <input className={fieldClass} value={tags} onChange={(e) => setTags(e.target.value)} placeholder={catalog.tags.slice(0, 3).join(", ") || "finance, crm"} />
              </Field>
              <Field label="Description (optional)">
                <input className={fieldClass} value={description} onChange={(e) => setDescription(e.target.value)} maxLength={400} />
              </Field>
            </div>

            <footer className="flex items-center justify-between gap-3 border-t border-slate-100 px-5 py-3 dark:border-border">
              <p className={cn("text-2xs", error ? "text-[#a8463d]" : "text-slate-400")} role={error ? "alert" : undefined}>
                {error ?? (missing.length ? `Still needed: ${missing.join(", ")}.` : "Ready to create.")}
              </p>
              <div className="flex gap-2">
                <button type="button" onClick={onClose} className="h-8 rounded-lg border border-slate-200 px-3 text-xs font-medium text-slate-700 hover:bg-slate-50">
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={missing.length > 0 || pending}
                  className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-[#2f6fed] px-3 text-xs font-medium text-white shadow-sm disabled:opacity-40"
                >
                  {pending ? <Loader2 className="size-3.5 animate-spin" /> : null}
                  Create monitor
                </button>
              </div>
            </footer>
          </motion.form>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

function Field({ label, className, children }: { label: string; className?: string; children: React.ReactNode }) {
  return (
    <label className={cn("block text-[11px] font-medium text-slate-500", className)}>
      {label}
      {children}
    </label>
  );
}
