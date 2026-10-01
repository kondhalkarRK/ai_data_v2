"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, Trash2, X } from "lucide-react";
import * as React from "react";

import { formatCount, formatInr } from "@/components/executive/cockpit/format";
import type {
  DataReliability,
  DimensionKey,
  Drilldown,
  RuleRow,
  Severity,
} from "@/components/reliability/types";
import {
  BAND_COLOUR,
  DIMENSION_COLOUR,
  DIMENSION_LABEL,
  EmptyNote,
  formatHours,
  formatScore,
  formatWhen,
  ScoreRing,
  SEVERITIES,
  SeverityChip,
  Sparkline,
  StatusPill,
  TRUST,
} from "@/components/reliability/ui";
import { cn } from "@/lib/utils";

export interface RuleEdits {
  enabled?: boolean;
  severity?: Severity;
  dimension?: DimensionKey;
  threshold?: number;
  owner?: string;
}

export function DrilldownPanel({
  data,
  drill,
  canEdit,
  pending,
  onNavigate,
  onBack,
  onClose,
  onUpdate,
  onDelete,
}: {
  data: DataReliability;
  drill: Drilldown | null;
  canEdit: boolean;
  pending: boolean;
  onNavigate: (next: Drilldown) => void;
  onBack?: () => void;
  onClose: () => void;
  onUpdate: (id: string, edits: RuleEdits) => void;
  onDelete: (id: string) => void;
}) {
  React.useEffect(() => {
    if (!drill) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drill, onClose]);

  return (
    <AnimatePresence>
      {drill ? (
        <>
          <motion.div
            key="scrim"
            className="fixed inset-0 z-50 bg-slate-900/20 backdrop-blur-[1px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.aside
            key="panel"
            role="dialog"
            aria-modal="true"
            aria-label="Reliability details"
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col border-l border-slate-200 bg-white shadow-2xl dark:border-border dark:bg-surface-raised"
            initial={{ x: 48, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 48, opacity: 0 }}
            transition={{ type: "spring", stiffness: 420, damping: 38 }}
          >
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3 dark:border-border">
              <div className="flex items-center gap-2">
                {onBack ? (
                  <button
                    type="button"
                    onClick={onBack}
                    className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                    aria-label="Back"
                  >
                    <ArrowLeft className="size-4" />
                  </button>
                ) : null}
                <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-[#2f6fed]">
                  {drill.kind === "dimension" ? "Dimension drilldown" : drill.kind === "rule" ? "Rule detail" : "Dataset detail"}
                </p>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                aria-label="Close details"
              >
                <X className="size-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-4">
              {drill.kind === "dimension" ? (
                <DimensionView data={data} dimension={drill.key} onNavigate={onNavigate} />
              ) : drill.kind === "rule" ? (
                <RuleView
                  data={data}
                  id={drill.id}
                  canEdit={canEdit}
                  pending={pending}
                  onNavigate={onNavigate}
                  onUpdate={onUpdate}
                  onDelete={onDelete}
                />
              ) : (
                <DatasetView data={data} name={drill.name} onNavigate={onNavigate} />
              )}
            </div>
          </motion.aside>
        </>
      ) : null}
    </AnimatePresence>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-5">
      <h4 className="mb-2 text-2xs font-semibold uppercase tracking-wide text-slate-500">{title}</h4>
      {children}
    </section>
  );
}

function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="rounded-xl bg-slate-50 px-3 py-2 dark:bg-muted">
      <p className="text-[10px] uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-0.5 truncate text-sm font-semibold tabular-nums text-slate-800 dark:text-foreground">{value}</p>
      {hint ? <p className="truncate text-[10px] text-slate-400">{hint}</p> : null}
    </div>
  );
}

function RuleList({ rules, onNavigate }: { rules: RuleRow[]; onNavigate: (next: Drilldown) => void }) {
  if (!rules.length) return <EmptyNote>No rules in this view.</EmptyNote>;
  return (
    <ul className="divide-y divide-slate-100 rounded-xl border border-slate-100 dark:divide-border dark:border-border">
      {rules.map((r) => (
        <li key={r.id}>
          <button
            type="button"
            onClick={() => onNavigate({ kind: "rule", id: r.id })}
            className="flex w-full items-center gap-3 px-3 py-2 text-left transition hover:bg-slate-50 dark:hover:bg-muted"
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium text-slate-800 dark:text-foreground">{r.name}</p>
              <p className="truncate text-[10px] text-slate-400">
                {r.datasetLabel} · {r.observed || r.description}
              </p>
            </div>
            <span className="w-14 text-right text-xs font-semibold tabular-nums text-slate-700">
              {r.passRate == null ? "—" : `${r.passRate.toFixed(1)}%`}
            </span>
            <span className="w-16">
              <StatusPill status={r.status} />
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function ImpactList({ rules }: { rules: RuleRow[] }) {
  const items = rules.filter((r) => r.status === "failing" && r.impact);
  if (!items.length) return <EmptyNote>No business impact: every check here is within its target.</EmptyNote>;
  return (
    <ul className="space-y-2">
      {items.map((r) => (
        <li key={r.id} className="rounded-xl border border-[#f0dfb4] bg-[#fffaf0] px-3 py-2 text-xs leading-relaxed text-slate-700">
          {r.impact}
          {r.assets.length ? (
            <span className="mt-1 block text-[10px] text-slate-500">Affects {r.assets.join(", ")}</span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function Failures({ rules }: { rules: RuleRow[] }) {
  const failing = rules.filter((r) => r.status === "failing" || r.status === "error");
  if (!failing.length) return <EmptyNote>No recent failures.</EmptyNote>;
  return (
    <ul className="space-y-2">
      {failing.map((r) => (
        <li key={r.id} className="rounded-xl border border-slate-100 px-3 py-2 dark:border-border">
          <div className="flex items-center justify-between gap-2">
            <p className="truncate text-xs font-medium text-slate-800 dark:text-foreground">{r.name}</p>
            <SeverityChip severity={r.severity} />
          </div>
          <p className="mt-0.5 text-[11px] text-slate-500">{r.observed}</p>
          {r.samples.length ? (
            <ul className="mt-1.5 space-y-0.5">
              {r.samples.slice(0, 3).map((s, i) => (
                <li key={i} className="truncate rounded bg-slate-50 px-2 py-0.5 font-mono text-[10px] text-slate-600 dark:bg-muted">
                  {s}
                </li>
              ))}
            </ul>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function DimensionView({
  data,
  dimension,
  onNavigate,
}: {
  data: DataReliability;
  dimension: DimensionKey;
  onNavigate: (next: Drilldown) => void;
}) {
  const card = data.dimensions.find((d) => d.key === dimension);
  const rules = data.rules
    .filter((r) => r.dimension === dimension)
    .sort((a, b) => (a.score ?? 101) - (b.score ?? 101));
  const datasetNames = [...new Set(rules.map((r) => r.dataset))];
  const datasets = data.datasets.filter((d) => datasetNames.includes(d.name));
  if (!card) return <EmptyNote>Dimension not found.</EmptyNote>;
  return (
    <>
      <div className="flex items-center gap-4">
        <div className="relative">
          <ScoreRing score={card.score} band={card.band} size={72} stroke={6} />
          <span
            className="absolute inset-0 flex items-center justify-center text-base font-semibold tabular-nums"
            style={{ color: BAND_COLOUR[card.band] }}
          >
            {card.score == null ? "—" : Math.round(card.score)}
          </span>
        </div>
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-lg font-semibold text-slate-900 dark:text-foreground">
            <span className="size-2.5 rounded-sm" style={{ backgroundColor: DIMENSION_COLOUR[dimension] }} />
            {card.label}
          </h2>
          <p className="text-xs text-slate-500">{card.question}</p>
          <p className="mt-1 text-[11px] text-slate-400">
            Score {formatScore(card.score)} · {Math.round(card.effectiveWeight ?? card.weight)}% of the trust score
          </p>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-3 gap-2">
        <Stat label="Rules" value={card.rules} />
        <Stat label="Passing" value={card.passing} />
        <Stat label="Failing" value={card.failing} hint={card.errored ? `${card.errored} not run` : undefined} />
      </div>
      <div className="mt-3 flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 dark:bg-muted">
        <span className="text-[11px] text-slate-500">Recent score history</span>
        <Sparkline values={card.sparkline} colour={DIMENSION_COLOUR[dimension]} width={180} height={28} />
      </div>
      <Block title="Business impact">
        <ImpactList rules={rules} />
      </Block>
      <Block title="Recent failures">
        <Failures rules={rules} />
      </Block>
      <Block title={`Rules (${rules.length})`}>
        <RuleList rules={rules} onNavigate={onNavigate} />
      </Block>
      <Block title="Datasets covered">
        <div className="flex flex-wrap gap-1.5">
          {datasets.map((d) => (
            <button
              key={d.name}
              type="button"
              onClick={() => onNavigate({ kind: "dataset", name: d.name })}
              className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-2.5 py-1 text-2xs text-slate-700 hover:border-[#8fb3f5] dark:border-border dark:text-foreground"
            >
              <span className="size-1.5 rounded-full" style={{ backgroundColor: BAND_COLOUR[d.band] }} />
              {d.label}
              <span className="tabular-nums text-slate-400">{formatScore(d.score)}</span>
            </button>
          ))}
        </div>
      </Block>
    </>
  );
}

function RuleView({
  data,
  id,
  canEdit,
  pending,
  onNavigate,
  onUpdate,
  onDelete,
}: {
  data: DataReliability;
  id: string;
  canEdit: boolean;
  pending: boolean;
  onNavigate: (next: Drilldown) => void;
  onUpdate: (id: string, edits: RuleEdits) => void;
  onDelete: (id: string) => void;
}) {
  const rule = data.rules.find((r) => r.id === id);
  if (!rule) return <EmptyNote>This rule is no longer in the catalog.</EmptyNote>;
  return (
    <RuleDetail
      key={`${rule.id}:${rule.threshold}:${rule.owner}`}
      rule={rule}
      canEdit={canEdit}
      pending={pending}
      onNavigate={onNavigate}
      onUpdate={onUpdate}
      onDelete={onDelete}
    />
  );
}

function RuleDetail({
  rule,
  canEdit,
  pending,
  onNavigate,
  onUpdate,
  onDelete,
}: {
  rule: RuleRow;
  canEdit: boolean;
  pending: boolean;
  onNavigate: (next: Drilldown) => void;
  onUpdate: (id: string, edits: RuleEdits) => void;
  onDelete: (id: string) => void;
}) {
  const [threshold, setThreshold] = React.useState<string>(String(rule.threshold));
  const [owner, setOwner] = React.useState<string>(rule.owner);
  const thresholdValue = Number(threshold);
  const thresholdDirty =
    threshold !== "" && Number.isFinite(thresholdValue) && thresholdValue >= 0 && thresholdValue <= 100 && thresholdValue !== rule.threshold;
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <SeverityChip severity={rule.severity} />
        <StatusPill status={rule.status} />
        {rule.custom ? (
          <span className="rounded-full bg-[#e3ecfd] px-2 py-0.5 text-2xs font-medium text-[#2f5fc4]">Custom monitor</span>
        ) : null}
      </div>
      <h2 className="mt-2 text-lg font-semibold text-slate-900 dark:text-foreground">{rule.name}</h2>
      <p className="mt-0.5 text-xs leading-relaxed text-slate-500">{rule.description}</p>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-500">
        <button type="button" className="hover:text-[#2f6fed]" onClick={() => onNavigate({ kind: "dimension", key: rule.dimension })}>
          {DIMENSION_LABEL[rule.dimension]}
        </button>
        <span>·</span>
        <button type="button" className="hover:text-[#2f6fed]" onClick={() => onNavigate({ kind: "dataset", name: rule.dataset })}>
          {rule.datasetLabel}
        </button>
        <span>·</span>
        <span>Owner {rule.owner}</span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Pass rate" value={rule.passRate == null ? "—" : `${rule.passRate.toFixed(2)}%`} hint={`target ${rule.threshold}%`} />
        <Stat label="Checked" value={formatCount(rule.total)} hint={rule.unit} />
        <Stat label="Failed" value={formatCount(rule.failed)} hint={rule.unit} />
        <Stat
          label="Value at risk"
          value={rule.valueAtRisk == null ? "—" : formatInr(rule.valueAtRisk)}
          hint={rule.durationMs ? `ran in ${rule.durationMs} ms` : undefined}
        />
      </div>
      <p className="mt-3 rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-700 dark:bg-muted dark:text-foreground">
        <span className="font-medium">Result: </span>
        {rule.observed || "Not run yet"}
      </p>
      <div className="mt-2 flex items-center justify-between text-[11px] text-slate-500">
        <span>
          Last run {formatWhen(rule.lastRunAt)}
          {rule.failingSince ? ` · failing since ${formatWhen(rule.failingSince)}` : ""}
          {!rule.failingSince && rule.lastFailureAt ? ` · last failed ${formatWhen(rule.lastFailureAt)}` : ""}
        </span>
        <Sparkline values={rule.sparkline} colour={TRUST.blue} width={110} height={22} />
      </div>

      <Block title="Business impact">
        {rule.status === "failing" && rule.impact ? (
          <p className="rounded-xl border border-[#f0dfb4] bg-[#fffaf0] px-3 py-2 text-xs leading-relaxed text-slate-700">{rule.impact}</p>
        ) : (
          <EmptyNote>Within target: no downstream impact right now.</EmptyNote>
        )}
        {rule.assets.length ? (
          <p className="mt-2 text-[11px] text-slate-500">Feeds: {rule.assets.join(", ")}</p>
        ) : null}
      </Block>

      {rule.samples.length ? (
        <Block title="Failing examples">
          <ul className="space-y-1">
            {rule.samples.map((s, i) => (
              <li key={i} className="truncate rounded-lg bg-slate-50 px-2.5 py-1 font-mono text-[11px] text-slate-600 dark:bg-muted" title={s}>
                {s}
              </li>
            ))}
          </ul>
        </Block>
      ) : null}

      {rule.tags.length ? (
        <Block title="Tags">
          <div className="flex flex-wrap gap-1">
            {rule.tags.map((t) => (
              <span key={t} className="rounded-full bg-slate-100 px-2 py-0.5 text-2xs text-slate-600 dark:bg-muted">
                #{t}
              </span>
            ))}
          </div>
        </Block>
      ) : null}

      {canEdit ? (
        <Block title="Manage">
          <div className="grid gap-3 rounded-xl border border-slate-100 p-3 dark:border-border">
            <label className="flex items-center justify-between gap-3 text-xs text-slate-700 dark:text-foreground">
              Monitoring enabled
              <Toggle checked={rule.enabled} disabled={pending} onChange={(enabled) => onUpdate(rule.id, { enabled })} />
            </label>
            <div className="grid grid-cols-2 gap-2">
              <label className="text-[11px] text-slate-500">
                Severity
                <select
                  className={fieldClass}
                  value={rule.severity}
                  disabled={pending}
                  onChange={(e) => onUpdate(rule.id, { severity: e.target.value as Severity })}
                >
                  {SEVERITIES.map((s) => (
                    <option key={s} value={s}>
                      {s[0]!.toUpperCase() + s.slice(1)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-[11px] text-slate-500">
                Dimension
                <select
                  className={fieldClass}
                  value={rule.dimension}
                  disabled={pending}
                  onChange={(e) => onUpdate(rule.id, { dimension: e.target.value as DimensionKey })}
                >
                  {Object.entries(DIMENSION_LABEL).map(([k, label]) => (
                    <option key={k} value={k}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-[11px] text-slate-500">
                Pass-rate target (%)
                <span className="mt-1 flex gap-1">
                  <input
                    className={cn(fieldClass, "mt-0")}
                    inputMode="decimal"
                    value={threshold}
                    onChange={(e) => setThreshold(e.target.value)}
                  />
                  <button
                    type="button"
                    disabled={!thresholdDirty || pending}
                    onClick={() => onUpdate(rule.id, { threshold: thresholdValue })}
                    className="rounded-lg bg-[#2f6fed] px-2.5 text-2xs font-medium text-white disabled:opacity-40"
                  >
                    Save
                  </button>
                </span>
              </label>
              <label className="text-[11px] text-slate-500">
                Owner
                <span className="mt-1 flex gap-1">
                  <input className={cn(fieldClass, "mt-0")} value={owner} onChange={(e) => setOwner(e.target.value)} />
                  <button
                    type="button"
                    disabled={!owner.trim() || owner.trim() === rule.owner || pending}
                    onClick={() => onUpdate(rule.id, { owner: owner.trim() })}
                    className="rounded-lg bg-[#2f6fed] px-2.5 text-2xs font-medium text-white disabled:opacity-40"
                  >
                    Save
                  </button>
                </span>
              </label>
            </div>
            {rule.custom ? (
              <button
                type="button"
                disabled={pending}
                onClick={() => onDelete(rule.id)}
                className="inline-flex items-center gap-1.5 justify-self-start text-2xs font-medium text-[#a8463d] hover:underline disabled:opacity-50"
              >
                <Trash2 className="size-3.5" /> Delete this monitor
              </button>
            ) : null}
          </div>
        </Block>
      ) : null}
    </>
  );
}

function DatasetView({
  data,
  name,
  onNavigate,
}: {
  data: DataReliability;
  name: string;
  onNavigate: (next: Drilldown) => void;
}) {
  const ds = data.datasets.find((d) => d.name === name);
  const rules = data.rules.filter((r) => r.dataset === name).sort((a, b) => (a.score ?? 101) - (b.score ?? 101));
  const fresh = data.freshness.find((f) => f.dataset === name);
  if (!ds) return <EmptyNote>Dataset not found.</EmptyNote>;
  return (
    <>
      <div className="flex items-center gap-4">
        <div className="relative">
          <ScoreRing score={ds.score} band={ds.band} size={72} stroke={6} />
          <span
            className="absolute inset-0 flex items-center justify-center text-base font-semibold tabular-nums"
            style={{ color: BAND_COLOUR[ds.band] }}
          >
            {ds.score == null ? "—" : Math.round(ds.score)}
          </span>
        </div>
        <div className="min-w-0">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-foreground">{ds.label}</h2>
          <p className="text-xs capitalize text-slate-500">
            {ds.domain} · {ds.kind}
            {ds.rank ? ` · ranked #${ds.rank} of ${data.datasets.filter((d) => d.rank).length}` : ""}
          </p>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Rows" value={ds.rows == null ? "—" : formatCount(ds.rows)} />
        <Stat label="Rules" value={ds.rules} hint={`${ds.passing} passing`} />
        <Stat label="Last refresh" value={formatWhen(ds.lastRefresh)} />
        <Stat
          label="Freshness"
          value={fresh ? fresh.status.replace("_", " ") : "—"}
          hint={fresh?.slaHours ? `SLA ${formatHours(fresh.slaHours)}` : undefined}
        />
      </div>
      {ds.topIssue ? (
        <p className="mt-3 rounded-xl border border-[#f0dfb4] bg-[#fffaf0] px-3 py-2 text-xs text-slate-700">{ds.topIssue}</p>
      ) : null}
      {ds.assets.length ? <p className="mt-2 text-[11px] text-slate-500">Feeds: {ds.assets.join(", ")}</p> : null}
      <Block title="Business impact">
        <ImpactList rules={rules} />
      </Block>
      <Block title="Recent failures">
        <Failures rules={rules} />
      </Block>
      <Block title={`Rules on this dataset (${rules.length})`}>
        <RuleList rules={rules} onNavigate={onNavigate} />
      </Block>
    </>
  );
}

export const fieldClass =
  "mt-1 h-8 w-full rounded-lg border border-slate-200 bg-white px-2 text-xs text-slate-800 outline-none focus:border-[#8fb3f5] focus:ring-2 focus:ring-[#2f6fed]/15 disabled:opacity-50 dark:border-border dark:bg-surface dark:text-foreground";

export function Toggle({
  checked,
  disabled,
  onChange,
  label,
}: {
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={(e) => {
        e.stopPropagation();
        onChange(!checked);
      }}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition disabled:opacity-50",
        checked ? "bg-[#14a3a1]" : "bg-slate-200",
      )}
    >
      <span className={cn("inline-block size-4 rounded-full bg-white shadow transition", checked ? "translate-x-4.5" : "translate-x-0.5")} />
    </button>
  );
}
