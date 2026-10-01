"use client";

import { ChevronDown, Plus, Search, X } from "lucide-react";
import * as React from "react";

import { ChartFrame } from "@/components/executive/cockpit/chart-frame";
import { fieldClass, Toggle } from "@/components/reliability/drilldown-panel";
import type {
  BulkAction,
  DataReliability,
  DimensionKey,
  RuleRow,
  RuleStatus,
  Severity,
  TrustFilters,
} from "@/components/reliability/types";
import {
  BAND_COLOUR,
  DIMENSION_COLOUR,
  DIMENSION_LABEL,
  EmptyNote,
  formatScore,
  formatWhen,
  SEVERITIES,
  SeverityChip,
  StatusPill,
  TRUST,
} from "@/components/reliability/ui";
import { cn } from "@/lib/utils";

const STATUSES: Array<{ value: RuleStatus; label: string }> = [
  { value: "failing", label: "Failing" },
  { value: "passing", label: "Passing" },
  { value: "error", label: "Not run" },
  { value: "no_data", label: "No data" },
  { value: "disabled", label: "Disabled" },
];

const BULK_ACTIONS: Array<{ value: BulkAction; label: string; input: "dimension" | "severity" | "text" | "tags" | null }> = [
  { value: "assign_dimension", label: "Assign dimension", input: "dimension" },
  { value: "set_severity", label: "Change severity", input: "severity" },
  { value: "assign_owner", label: "Assign owner", input: "text" },
  { value: "add_tags", label: "Add tags", input: "tags" },
  { value: "remove_tags", label: "Remove tags", input: "tags" },
  { value: "enable", label: "Enable", input: null },
  { value: "disable", label: "Disable", input: null },
];

export interface BulkRequest {
  ruleIds: string[];
  action: BulkAction;
  value?: string;
  tags?: string[];
}

export function RulesCatalog({
  data,
  filters,
  onFilter,
  canEdit,
  pending,
  onOpenRule,
  onToggle,
  onBulk,
  onCreate,
  className,
}: {
  data: DataReliability;
  filters: TrustFilters;
  onFilter: (patch: TrustFilters) => void;
  canEdit: boolean;
  pending: boolean;
  onOpenRule: (id: string) => void;
  onToggle: (id: string, enabled: boolean) => void;
  onBulk: (request: BulkRequest) => Promise<boolean>;
  onCreate: () => void;
  className?: string;
}) {
  const [query, setQuery] = React.useState("");
  const [picked, setSelected] = React.useState<Set<string>>(new Set());
  const [collapsed, setCollapsed] = React.useState<Set<DimensionKey>>(new Set());

  const q = query.trim().toLowerCase();
  const rows = data.rules.filter(
    (r) =>
      (!filters.dimension || r.dimension === filters.dimension) &&
      (!filters.dataset || r.dataset === filters.dataset) &&
      (!filters.severity || r.severity === filters.severity) &&
      (!filters.status || r.status === filters.status) &&
      (!q ||
        r.name.toLowerCase().includes(q) ||
        r.description.toLowerCase().includes(q) ||
        r.owner.toLowerCase().includes(q) ||
        r.datasetLabel.toLowerCase().includes(q) ||
        r.tags.some((t) => t.includes(q))),
  );
  const groups = data.dimensions
    .map((d) => ({ card: d, rules: rows.filter((r) => r.dimension === d.key).sort(byAttention) }))
    .filter((g) => g.rules.length);

  const known = new Set(data.rules.map((r) => r.id));
  const selected = new Set([...picked].filter((id) => known.has(id)));
  const visibleIds = rows.map((r) => r.id);
  const allVisible = visibleIds.length > 0 && visibleIds.every((id) => selected.has(id));
  const toggle = (id: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const datasets = [...new Map(data.rules.map((r) => [r.dataset, r.datasetLabel])).entries()].sort((a, b) =>
    a[1].localeCompare(b[1]),
  );
  const filtered = Boolean(filters.dimension || filters.dataset || filters.severity || filters.status || q);

  return (
    <ChartFrame
      title="DQ rules catalog"
      subtitle={`${rows.length} of ${data.rules.length} rules · grouped by dimension · click a rule for its evidence`}
      exportName="dq-rules-catalog"
      png={false}
      className={className}
      controls={
        canEdit ? (
          <button
            type="button"
            onClick={onCreate}
            className="mr-1 inline-flex h-7 items-center gap-1 rounded-lg bg-[#2f6fed] px-2.5 text-2xs font-medium text-white shadow-sm hover:bg-[#285fd0]"
          >
            <Plus className="size-3.5" /> New monitor
          </button>
        ) : null
      }
      csv={() =>
        rows.map((r) => ({
          rule: r.name,
          dimension: DIMENSION_LABEL[r.dimension],
          dataset: r.datasetLabel,
          severity: r.severity,
          status: r.status,
          pass_rate: r.passRate,
          target: r.threshold,
          checked: r.total,
          failed: r.failed,
          result: r.observed,
          last_run: r.lastRunAt ?? "",
          owner: r.owner,
          tags: r.tags.join(" "),
          enabled: r.enabled,
        }))
      }
    >
      {(expanded) => (
        <div className={cn("flex flex-col", expanded && "h-full")}>
          <div className="flex flex-wrap items-center gap-2">
            <label className="relative min-w-48 flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-slate-400" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search rules, owners, tags…"
                className={cn(fieldClass, "mt-0 pl-8")}
              />
            </label>
            <FilterSelect
              label="Dimension"
              value={filters.dimension ?? ""}
              onChange={(v) => onFilter({ dimension: (v || undefined) as DimensionKey | undefined })}
              options={Object.entries(DIMENSION_LABEL).map(([value, label]) => ({ value, label }))}
            />
            <FilterSelect
              label="Dataset"
              value={filters.dataset ?? ""}
              onChange={(v) => onFilter({ dataset: v || undefined })}
              options={datasets.map(([value, label]) => ({ value, label }))}
            />
            <FilterSelect
              label="Severity"
              value={filters.severity ?? ""}
              onChange={(v) => onFilter({ severity: (v || undefined) as Severity | undefined })}
              options={SEVERITIES.map((s) => ({ value: s, label: s[0]!.toUpperCase() + s.slice(1) }))}
            />
            <FilterSelect
              label="Status"
              value={filters.status ?? ""}
              onChange={(v) => onFilter({ status: (v || undefined) as RuleStatus | undefined })}
              options={STATUSES}
            />
            {filtered ? (
              <button
                type="button"
                className="text-2xs font-medium text-[#2f6fed] hover:underline"
                onClick={() => {
                  setQuery("");
                  onFilter({ dimension: undefined, dataset: undefined, severity: undefined, status: undefined });
                }}
              >
                Reset
              </button>
            ) : null}
          </div>

          {canEdit && selected.size ? (
            <BulkBar
              count={selected.size}
              pending={pending}
              owners={data.catalog.owners}
              onClear={() => setSelected(new Set())}
              onApply={async (action, value, tags) => {
                const ok = await onBulk({ ruleIds: [...selected], action, value, tags });
                if (ok) setSelected(new Set());
              }}
            />
          ) : null}

          <div className={cn("mt-3 overflow-auto rounded-xl border border-slate-100 dark:border-border", expanded ? "flex-1" : "max-h-[34rem]")}>
            {groups.length ? (
              <table className="w-full min-w-[60rem] text-left text-xs">
                <thead className="sticky top-0 z-[1] bg-slate-50/95 text-[10px] uppercase tracking-wide text-slate-500 backdrop-blur dark:bg-muted">
                  <tr>
                    {canEdit ? (
                      <th className="w-8 px-3 py-2">
                        <input
                          type="checkbox"
                          aria-label="Select all visible rules"
                          checked={allVisible}
                          onChange={() =>
                            setSelected((current) => {
                              const next = new Set(current);
                              for (const id of visibleIds) {
                                if (allVisible) next.delete(id);
                                else next.add(id);
                              }
                              return next;
                            })
                          }
                          className="accent-[#2f6fed]"
                        />
                      </th>
                    ) : null}
                    <th className="px-3 py-2 font-medium">Rule name</th>
                    <th className="px-3 py-2 font-medium">Dimension</th>
                    <th className="px-3 py-2 font-medium">Dataset</th>
                    <th className="px-3 py-2 font-medium">Severity</th>
                    <th className="px-3 py-2 font-medium">Last run</th>
                    <th className="px-3 py-2 font-medium">Pass rate</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 font-medium">Owner</th>
                    {canEdit ? <th className="px-3 py-2 font-medium">On</th> : null}
                  </tr>
                </thead>
                {groups.map(({ card, rules }) => {
                  const isCollapsed = collapsed.has(card.key);
                  return (
                    <tbody key={card.key} className="divide-y divide-slate-100 dark:divide-border">
                      <tr className="bg-white dark:bg-surface-raised">
                        <td colSpan={canEdit ? 10 : 8} className="px-3 pb-1.5 pt-3">
                          <button
                            type="button"
                            className="flex items-center gap-2 text-xs font-semibold text-slate-700 dark:text-foreground"
                            onClick={() =>
                              setCollapsed((current) => {
                                const next = new Set(current);
                                if (next.has(card.key)) next.delete(card.key);
                                else next.add(card.key);
                                return next;
                              })
                            }
                          >
                            <ChevronDown className={cn("size-3.5 text-slate-400 transition", isCollapsed && "-rotate-90")} />
                            <span className="size-2 rounded-sm" style={{ backgroundColor: DIMENSION_COLOUR[card.key] }} />
                            {card.label}
                            <span className="font-normal text-slate-400">
                              {rules.length} rule{rules.length === 1 ? "" : "s"} · score{" "}
                              <span className="tabular-nums" style={{ color: BAND_COLOUR[card.band] }}>
                                {formatScore(card.score)}
                              </span>
                            </span>
                          </button>
                        </td>
                      </tr>
                      {isCollapsed
                        ? null
                        : rules.map((r) => (
                            <RuleRowView
                              key={r.id}
                              rule={r}
                              canEdit={canEdit}
                              pending={pending}
                              checked={selected.has(r.id)}
                              onCheck={() => toggle(r.id)}
                              onOpen={() => onOpenRule(r.id)}
                              onToggle={(enabled) => onToggle(r.id, enabled)}
                            />
                          ))}
                    </tbody>
                  );
                })}
              </table>
            ) : (
              <div className="p-4">
                <EmptyNote>No rules match these filters.</EmptyNote>
              </div>
            )}
          </div>
        </div>
      )}
    </ChartFrame>
  );
}

const STATUS_ORDER: Record<RuleStatus, number> = { failing: 0, error: 1, no_data: 2, passing: 3, disabled: 4 };
const SEVERITY_ORDER: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3 };

function byAttention(a: RuleRow, b: RuleRow): number {
  return (
    STATUS_ORDER[a.status] - STATUS_ORDER[b.status] ||
    SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity] ||
    a.name.localeCompare(b.name)
  );
}

function RuleRowView({
  rule,
  canEdit,
  pending,
  checked,
  onCheck,
  onOpen,
  onToggle,
}: {
  rule: RuleRow;
  canEdit: boolean;
  pending: boolean;
  checked: boolean;
  onCheck: () => void;
  onOpen: () => void;
  onToggle: (enabled: boolean) => void;
}) {
  return (
    <tr
      onClick={onOpen}
      className={cn(
        "cursor-pointer transition hover:bg-[#f5f8ff] dark:hover:bg-muted",
        checked && "bg-[#f1f6ff]",
        !rule.enabled && "text-slate-400",
      )}
    >
      {canEdit ? (
        <td className="px-3 py-2.5" onClick={(e) => e.stopPropagation()}>
          <input
            type="checkbox"
            aria-label={`Select ${rule.name}`}
            checked={checked}
            onChange={onCheck}
            className="accent-[#2f6fed]"
          />
        </td>
      ) : null}
      <td className="max-w-[18rem] px-3 py-2.5">
        <p className="truncate font-medium text-slate-800 dark:text-foreground">
          {rule.name}
          {rule.custom ? <span className="ml-1.5 rounded bg-[#e3ecfd] px-1 py-px text-[9px] font-semibold text-[#2f5fc4]">CUSTOM</span> : null}
        </p>
        <p className="truncate text-[10px] text-slate-400" title={rule.observed || rule.description}>
          {rule.observed || rule.description}
        </p>
      </td>
      <td className="whitespace-nowrap px-3 py-2.5 text-slate-600">{DIMENSION_LABEL[rule.dimension]}</td>
      <td className="max-w-[10rem] truncate px-3 py-2.5 text-slate-600">{rule.datasetLabel}</td>
      <td className="px-3 py-2.5">
        <SeverityChip severity={rule.severity} />
      </td>
      <td className="whitespace-nowrap px-3 py-2.5 text-slate-500">{formatWhen(rule.lastRunAt)}</td>
      <td className="px-3 py-2.5">
        <PassRate rate={rule.passRate} target={rule.threshold} status={rule.status} />
      </td>
      <td className="whitespace-nowrap px-3 py-2.5">
        <StatusPill status={rule.status} />
      </td>
      <td className="max-w-[9rem] truncate px-3 py-2.5 text-slate-600">{rule.owner}</td>
      {canEdit ? (
        <td className="px-3 py-2.5">
          <Toggle checked={rule.enabled} disabled={pending} onChange={onToggle} label={`Enable ${rule.name}`} />
        </td>
      ) : null}
    </tr>
  );
}

function PassRate({ rate, target, status }: { rate: number | null; target: number; status: RuleStatus }) {
  if (rate == null) return <span className="text-slate-300">—</span>;
  const colour = status === "failing" ? TRUST.amber : TRUST.green;
  return (
    <div className="flex items-center gap-2" title={`Target ${target}%`}>
      <span className="w-12 text-right font-semibold tabular-nums text-slate-700 dark:text-foreground">
        {rate >= 99.995 ? "100%" : `${rate.toFixed(rate >= 99 ? 2 : 1)}%`}
      </span>
      <span className="relative h-1.5 w-16 rounded-full bg-slate-100">
        <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${Math.max(2, rate)}%`, backgroundColor: colour }} />
        <span className="absolute -top-0.5 h-2.5 w-px bg-slate-400" style={{ left: `${target}%` }} />
      </span>
    </div>
  );
}

const ALL_LABEL: Record<string, string> = { Severity: "All severities", Status: "Any status" };

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={cn(fieldClass, "mt-0 w-auto min-w-28", value && "border-[#8fb3f5] bg-[#f1f6ff] text-[#2f5fc4]")}
    >
      <option value="">{ALL_LABEL[label] ?? `All ${label.toLowerCase()}s`}</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

function BulkBar({
  count,
  pending,
  owners,
  onClear,
  onApply,
}: {
  count: number;
  pending: boolean;
  owners: string[];
  onClear: () => void;
  onApply: (action: BulkAction, value?: string, tags?: string[]) => void;
}) {
  const [action, setAction] = React.useState<BulkAction>("assign_dimension");
  const [value, setValue] = React.useState<string>("");
  const spec = BULK_ACTIONS.find((a) => a.value === action)!;
  const tags = value
    .split(/[,\s]+/)
    .map((t) => t.trim())
    .filter(Boolean);
  const ready = spec.input == null || (spec.input === "tags" ? tags.length > 0 : value.trim().length > 0);

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-[#c9dafb] bg-[#f1f6ff] px-3 py-2 dark:border-border dark:bg-muted">
      <span className="text-xs font-semibold text-[#2f5fc4]">{count} selected</span>
      <select
        aria-label="Bulk action"
        value={action}
        onChange={(e) => {
          setAction(e.target.value as BulkAction);
          setValue("");
        }}
        className={cn(fieldClass, "mt-0 w-auto")}
      >
        {BULK_ACTIONS.map((a) => (
          <option key={a.value} value={a.value}>
            {a.label}
          </option>
        ))}
      </select>
      {spec.input === "dimension" ? (
        <select aria-label="New dimension" value={value} onChange={(e) => setValue(e.target.value)} className={cn(fieldClass, "mt-0 w-auto")}>
          <option value="">Choose dimension…</option>
          {Object.entries(DIMENSION_LABEL).map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </select>
      ) : spec.input === "severity" ? (
        <select aria-label="New severity" value={value} onChange={(e) => setValue(e.target.value)} className={cn(fieldClass, "mt-0 w-auto")}>
          <option value="">Choose severity…</option>
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>
              {s[0]!.toUpperCase() + s.slice(1)}
            </option>
          ))}
        </select>
      ) : spec.input ? (
        <>
          <input
            aria-label={spec.input === "tags" ? "Tags to change" : "New owner"}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={spec.input === "tags" ? "e.g. finance, month-end" : "Owner team"}
            list={spec.input === "text" ? "dq-owner-options" : undefined}
            className={cn(fieldClass, "mt-0 w-48")}
          />
          {spec.input === "text" ? (
            <datalist id="dq-owner-options">
              {owners.map((o) => (
                <option key={o} value={o} />
              ))}
            </datalist>
          ) : null}
        </>
      ) : null}
      <button
        type="button"
        disabled={!ready || pending}
        onClick={() => onApply(action, spec.input && spec.input !== "tags" ? value.trim() : undefined, spec.input === "tags" ? tags : undefined)}
        className="h-8 rounded-lg bg-[#2f6fed] px-3 text-2xs font-medium text-white shadow-sm disabled:opacity-40"
      >
        Apply
      </button>
      <button type="button" onClick={onClear} className="ml-auto rounded-md p-1 text-slate-400 hover:text-slate-700" aria-label="Clear selection">
        <X className="size-4" />
      </button>
    </div>
  );
}
