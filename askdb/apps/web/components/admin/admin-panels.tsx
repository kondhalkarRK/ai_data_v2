"use client";

import {
  Database,
  Loader2,
  Network,
  RefreshCw,
  Save,
  ShieldCheck,
  Sparkles,
  Workflow,
} from "lucide-react";
import * as React from "react";

import { DailyTrend, MODE_COLOR, MODE_LABEL, ModeDonut, ModeLegend, UserBars } from "@/components/admin/charts";
import { UsageMeter } from "@/components/governance/usage-meter";
import { LoadingState } from "@/components/loading/loading-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Section } from "@/components/ui/page-shell";
import { EmptyState, StatusPill } from "@/components/ui/status-pill";
import {
  type AdminActionResult,
  type ExecutionMode,
  useAdminAction,
  useAudit,
  useDqRules,
  useGovernance,
  useLlmSettings,
  useUpdateLlmSettings,
  useUsageOverview,
} from "@/hooks/use-admin";
import { ApiError } from "@/lib/api-client";
import { cn } from "@/lib/utils";

// --- shared ---------------------------------------------------------------------

function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "The request failed. Check that the API and database are running.";
}

function when(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function ms(value: number | null): string {
  if (value == null) return "—";
  return value >= 1000 ? `${(value / 1000).toFixed(1)} s` : `${value} ms`;
}

function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card>
      <CardContent className="pt-4">
        <CardDescription>{label}</CardDescription>
        <p className="mt-1 text-2xl font-semibold tabular-nums text-foreground">{value}</p>
        {hint ? <p className="mt-0.5 truncate text-xs text-muted-foreground">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}

function Failed({ error }: { error: unknown }) {
  return <EmptyState title="This view could not be loaded" detail={errorText(error)} />;
}

function DaysPicker({ days, onChange }: { days: number; onChange: (days: number) => void }) {
  return (
    <div className="inline-flex rounded-[var(--radius-control)] border border-border bg-muted/30 p-0.5 text-xs">
      {[7, 30, 90].map((value) => (
        <button
          key={value}
          type="button"
          aria-pressed={days === value}
          onClick={() => onChange(value)}
          className={cn(
            "rounded-[var(--radius-control)] px-3 py-1",
            days === value ? "bg-background font-medium text-foreground shadow-sm" : "text-muted-foreground",
          )}
        >
          {value} days
        </button>
      ))}
    </div>
  );
}

function ModeBadge({ mode }: { mode: ExecutionMode }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium">
      <span className="size-2 rounded-full" style={{ backgroundColor: MODE_COLOR[mode] }} />
      {MODE_LABEL[mode]}
    </span>
  );
}

function ResultNotice({ result, error }: { result: AdminActionResult | null; error: unknown }) {
  if (error) {
    return (
      <p role="alert" className="rounded-[var(--radius-control)] bg-danger/10 px-3 py-2 text-sm text-danger">
        {errorText(error)}
      </p>
    );
  }
  if (!result) return null;
  return (
    <p role="status" className="rounded-[var(--radius-control)] bg-success/10 px-3 py-2 text-sm text-success">
      {result.message}
    </p>
  );
}

const TABLE_HEAD = "px-3 py-2 text-left text-xs font-medium text-muted-foreground";
const TABLE_CELL = "px-3 py-2 align-top";

// --- 1. AI Governance -----------------------------------------------------------

export function AiGovernancePanel() {
  const settings = useLlmSettings();
  const update = useUpdateLlmSettings();
  const [draft, setDraft] = React.useState<{
    provider: string;
    model: string;
    temperature: number;
    maxTokens: number;
  } | null>(null);

  const current = settings.data?.current;
  const form = draft ?? (current
    ? { provider: current.provider, model: current.model, temperature: current.temperature, maxTokens: current.maxTokens }
    : null);

  if (settings.isPending) return <LoadingState title="Loading AI settings" />;
  if (settings.isError || !current || !form) return <Failed error={settings.error} />;

  const providers = settings.data.providers;
  const provider = providers.find((p) => p.id === form.provider);
  const dirty =
    form.provider !== current.provider ||
    form.model !== current.model ||
    form.temperature !== current.temperature ||
    form.maxTokens !== current.maxTokens;

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi label="Current provider" value={current.providerLabel} />
        <Kpi label="Current model" value={current.model} />
        <Kpi label="Temperature" value={String(current.temperature)} />
        <Kpi label="Max tokens" value={current.maxTokens.toLocaleString()} />
      </div>
      <p className="-mt-3 text-xs text-muted-foreground">
        {current.updatedBy
          ? `Last changed by ${current.updatedBy}${current.updatedAt ? ` on ${when(current.updatedAt)}` : ""}.`
          : "Using the server defaults. Changes apply to every user's next AI Chat question."}
      </p>

      <Card>
        <CardContent className="space-y-5 pt-5">
          <CardTitle className="text-base">Change LLM settings</CardTitle>
          <div className="grid gap-5 md:grid-cols-2">
            <div className="space-y-1.5">
              <label htmlFor="llm-provider" className="text-sm font-medium">Provider</label>
              <select
                id="llm-provider"
                className="h-9 w-full rounded-[var(--radius-control)] border border-border bg-background px-3 text-sm"
                value={form.provider}
                onChange={(event) => {
                  const next = providers.find((p) => p.id === event.target.value);
                  setDraft({ ...form, provider: event.target.value, model: next?.models[0] ?? form.model });
                }}
              >
                {providers.map((option) => (
                  <option key={option.id} value={option.id} disabled={!option.configured}>
                    {option.label}
                    {option.configured ? "" : " (not configured)"}
                  </option>
                ))}
              </select>
              <p className="text-xs text-muted-foreground">
                Providers need their API key or endpoint in the API environment before they can be selected.
              </p>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="llm-model" className="text-sm font-medium">Model</label>
              <Input
                id="llm-model"
                list="llm-model-options"
                value={form.model}
                onChange={(event) => setDraft({ ...form, model: event.target.value })}
              />
              <datalist id="llm-model-options">
                {(provider?.models ?? []).map((model) => (
                  <option key={model} value={model} />
                ))}
              </datalist>
              <p className="text-xs text-muted-foreground">Pick a suggested model or type the provider&apos;s model name.</p>
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between">
                <label htmlFor="llm-temperature" className="text-sm font-medium">Temperature</label>
                <span className="text-xs tabular-nums text-muted-foreground">{form.temperature.toFixed(2)}</span>
              </div>
              <input
                id="llm-temperature"
                type="range"
                min={0}
                max={1.5}
                step={0.05}
                value={form.temperature}
                onChange={(event) => setDraft({ ...form, temperature: Number(event.target.value) })}
                className="w-full"
              />
              <p className="text-xs text-muted-foreground">0.1–0.3 keeps SQL generation consistent.</p>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="llm-max-tokens" className="text-sm font-medium">Max tokens per completion</label>
              <Input
                id="llm-max-tokens"
                type="number"
                min={64}
                max={8000}
                step={50}
                value={form.maxTokens}
                onChange={(event) => setDraft({ ...form, maxTokens: Number(event.target.value) })}
              />
              <p className="text-xs text-muted-foreground">Between 64 and 8,000.</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button
              disabled={!dirty || update.isPending || !form.model.trim()}
              onClick={() =>
                update.mutate(form, {
                  onSuccess: () => setDraft(null),
                })
              }
            >
              {update.isPending ? <Loader2 className="animate-spin" /> : <Save />}
              Save settings
            </Button>
            {dirty ? (
              <Button variant="ghost" size="sm" onClick={() => setDraft(null)}>
                Discard
              </Button>
            ) : null}
            {update.isSuccess && !dirty ? (
              <span className="text-sm text-success">Saved. The change is recorded in the Audit Center.</span>
            ) : null}
          </div>
          {update.isError ? <ResultNotice result={null} error={update.error} /> : null}
        </CardContent>
      </Card>
    </div>
  );
}

// --- 2. Hybrid AI Governance Dashboard ------------------------------------------

export function GovernanceDashboardPanel() {
  const [days, setDays] = React.useState(30);
  const overview = useGovernance(days);

  if (overview.isPending) return <LoadingState title="Loading governance dashboard" />;
  if (overview.isError || !overview.data) return <Failed error={overview.error} />;
  const data = overview.data;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          How AI Chat answered questions: semantic layer only, LLM, both, or cache.
        </p>
        <DaysPicker days={days} onChange={setDays} />
      </div>
      <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
        <Kpi label="Total questions" value={data.kpis.totalQuestions.toLocaleString()} />
        <Kpi label="Schema queries" value={data.kpis.schemaQueries.toLocaleString()} />
        <Kpi label="LLM queries" value={data.kpis.llmQueries.toLocaleString()} />
        <Kpi label="Hybrid queries" value={data.kpis.hybridQueries.toLocaleString()} />
        <Kpi label="Cached queries" value={data.kpis.cachedQueries.toLocaleString()} />
        <Kpi label="Avg response time" value={ms(data.kpis.avgResponseMs)} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardContent className="space-y-4 pt-5">
            <CardTitle className="text-sm">Query distribution</CardTitle>
            <ModeDonut data={data.distribution} />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-4 pt-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle className="text-sm">Usage by user</CardTitle>
              <ModeLegend />
            </div>
            <UserBars data={data.byUser} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="space-y-3 pt-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle className="text-sm">Daily query trend</CardTitle>
            <ModeLegend />
          </div>
          <DailyTrend data={data.dailyTrend} />
        </CardContent>
      </Card>

      <Section title="Recent questions" description="Latest 50 AI Chat questions across all users.">
        <Card>
          <CardContent className="overflow-x-auto p-0">
            {data.recent.length ? (
              <table className="w-full text-sm">
                <thead className="border-b border-border/70">
                  <tr>
                    <th className={TABLE_HEAD}>User</th>
                    <th className={TABLE_HEAD}>Question</th>
                    <th className={TABLE_HEAD}>Execution mode</th>
                    <th className={cn(TABLE_HEAD, "text-right")}>Response time</th>
                    <th className={TABLE_HEAD}>Timestamp</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent.map((row) => (
                    <tr key={row.id} className="border-b border-border/40 last:border-0">
                      <td className={cn(TABLE_CELL, "font-medium")}>{row.user}</td>
                      <td className={cn(TABLE_CELL, "max-w-md text-muted-foreground")}>{row.question ?? "—"}</td>
                      <td className={TABLE_CELL}><ModeBadge mode={row.mode} /></td>
                      <td className={cn(TABLE_CELL, "text-right tabular-nums")}>{ms(row.responseMs)}</td>
                      <td className={cn(TABLE_CELL, "whitespace-nowrap text-muted-foreground")}>{when(row.createdAt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <EmptyState className="m-4" title="No questions yet" detail="Questions appear here as soon as anyone uses AI Chat." />
            )}
          </CardContent>
        </Card>
      </Section>
    </div>
  );
}

// --- 3. LLM Usage Monitoring ----------------------------------------------------

export function LlmUsagePanel() {
  const [days, setDays] = React.useState(30);
  const usage = useUsageOverview(days);

  if (usage.isPending) return <LoadingState title="Loading LLM usage" />;
  if (usage.isError || !usage.data) return <Failed error={usage.error} />;
  const data = usage.data;

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <DaysPicker days={days} onChange={setDays} />
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi label="Total LLM calls" value={data.kpis.totalLlmCalls.toLocaleString()} hint="Questions that used tokens" />
        <Kpi label="Total tokens" value={data.kpis.totalTokens.toLocaleString()} />
        <Kpi label="Most used model" value={data.kpis.mostUsedModel ?? "—"} />
        <Kpi label="Active users" value={data.kpis.activeUsers.toLocaleString()} />
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <Card>
          <CardContent className="space-y-3 pt-5">
            <CardTitle className="text-sm">Top users</CardTitle>
            {data.topUsers.length ? (
              <ol className="space-y-2 text-sm">
                {data.topUsers.map((row, index) => (
                  <li key={row.userId} className="flex items-center justify-between gap-3">
                    <span className="truncate">
                      <span className="mr-2 text-muted-foreground">{index + 1}.</span>
                      <span className="font-medium">{row.user}</span>
                    </span>
                    <span className="tabular-nums text-muted-foreground">
                      {row.tokens.toLocaleString()} tokens · {row.calls} calls
                    </span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-sm text-muted-foreground">No usage yet.</p>
            )}
            {data.models.length ? (
              <div className="border-t border-border/60 pt-3">
                <CardDescription className="mb-2">Calls by model</CardDescription>
                {data.models.map((row) => (
                  <div key={row.model} className="flex justify-between text-sm">
                    <span className="truncate">{row.model}</span>
                    <span className="tabular-nums text-muted-foreground">{row.calls}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead className="border-b border-border/70">
                <tr>
                  <th className={TABLE_HEAD}>User</th>
                  <th className={cn(TABLE_HEAD, "text-right")}>Calls</th>
                  <th className={cn(TABLE_HEAD, "text-right")}>Tokens</th>
                  <th className={cn(TABLE_HEAD, "text-right")}>Avg response</th>
                  <th className={cn(TABLE_HEAD, "min-w-44")}>This week</th>
                </tr>
              </thead>
              <tbody>
                {data.users.map((row) => (
                  <tr key={row.userId} className="border-b border-border/40 last:border-0">
                    <td className={TABLE_CELL}>
                      <span className="font-medium">{row.user}</span>
                      <span className="ml-2 text-2xs uppercase text-muted-foreground">{row.role}</span>
                    </td>
                    <td className={cn(TABLE_CELL, "text-right tabular-nums")}>{row.calls.toLocaleString()}</td>
                    <td className={cn(TABLE_CELL, "text-right tabular-nums")}>{row.tokens.toLocaleString()}</td>
                    <td className={cn(TABLE_CELL, "text-right tabular-nums")}>{ms(row.avgResponseMs)}</td>
                    <td className={TABLE_CELL}>
                      <div className="space-y-2">
                        <UsageMeter compact label="Tokens" used={row.weekTokens} limit={row.tokenLimit} unit="" />
                        <UsageMeter compact label="Calls" used={row.weekCalls} limit={row.callLimit} unit="" />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// --- 4. Data Trust Administration ------------------------------------------------

export function TrustAdminPanel() {
  const rules = useDqRules();
  const action = useAdminAction();
  const pending = action.isPending ? action.variables?.key : null;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2">
        <ActionCard
          icon={RefreshCw}
          title="Refresh DQ Rules"
          detail="Reload rule definitions and admin overrides for the active industry."
          busy={pending === "dq-rules"}
          disabled={action.isPending}
          onRun={() => action.mutate({ key: "dq-rules", path: "dq/refresh-rules" })}
        />
        <ActionCard
          icon={ShieldCheck}
          title="Refresh Trust Scores"
          detail="Run every enabled rule against the warehouse and recalculate the trust score."
          busy={pending === "dq-scores"}
          disabled={action.isPending}
          onRun={() => action.mutate({ key: "dq-scores", path: "dq/refresh-scores" })}
        />
      </div>
      <ResultNotice result={action.data ?? null} error={action.error} />

      <Section title="Enable / disable DQ rules" description="Disabled rules are skipped in trust scoring.">
        {rules.isPending ? (
          <LoadingState title="Loading rules" size="sm" />
        ) : rules.isError || !rules.data ? (
          <Failed error={rules.error} />
        ) : (
          <Card>
            <CardContent className="overflow-x-auto p-0">
              <table className="w-full text-sm">
                <thead className="border-b border-border/70">
                  <tr>
                    <th className={TABLE_HEAD}>Rule</th>
                    <th className={TABLE_HEAD}>Dimension</th>
                    <th className={TABLE_HEAD}>Dataset</th>
                    <th className={TABLE_HEAD}>Severity</th>
                    <th className={TABLE_HEAD}>Status</th>
                    <th className={TABLE_HEAD} />
                  </tr>
                </thead>
                <tbody>
                  {rules.data.map((rule) => {
                    const key = `rule-${rule.id}`;
                    return (
                      <tr key={rule.id} className="border-b border-border/40 last:border-0">
                        <td className={TABLE_CELL}>
                          <p className="font-medium">{rule.name}</p>
                          <p className="text-xs text-muted-foreground">{rule.id}</p>
                        </td>
                        <td className={cn(TABLE_CELL, "capitalize")}>{rule.dimension}</td>
                        <td className={TABLE_CELL}>{rule.dataset}</td>
                        <td className={cn(TABLE_CELL, "capitalize")}>{rule.severity}</td>
                        <td className={TABLE_CELL}>
                          <StatusPill tone={rule.enabled ? "ok" : "neutral"} label={rule.enabled ? "Enabled" : "Disabled"} />
                        </td>
                        <td className={cn(TABLE_CELL, "text-right")}>
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={action.isPending}
                            onClick={() =>
                              action.mutate({
                                key,
                                path: `dq/rules/${encodeURIComponent(rule.id)}/toggle`,
                                body: { enabled: !rule.enabled },
                              })
                            }
                          >
                            {pending === key ? <Loader2 className="animate-spin" /> : null}
                            {rule.enabled ? "Disable" : "Enable"}
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </CardContent>
          </Card>
        )}
      </Section>
    </div>
  );
}

// --- 5. Semantic Administration --------------------------------------------------

const SEMANTIC_ACTIONS = [
  {
    key: "catalog",
    icon: Database,
    title: "Refresh Entity Catalog",
    detail: "Re-read live values and aliases for every business column from the warehouse.",
  },
  {
    key: "metadata",
    icon: Workflow,
    title: "Refresh Semantic Metadata",
    detail: "Reload the semantic pack (tables, measures, dimensions, glossary) from disk.",
  },
  {
    key: "graph",
    icon: Network,
    title: "Refresh Knowledge Graph",
    detail: "Rebuild the knowledge graph from the current semantic model.",
  },
  {
    key: "cache",
    icon: Sparkles,
    title: "Refresh Semantic Cache",
    detail: "Clear cached answers so the next questions are recomputed.",
  },
] as const;

export function SemanticAdminPanel() {
  const action = useAdminAction();
  const pending = action.isPending ? action.variables?.key : null;
  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        {SEMANTIC_ACTIONS.map((item) => (
          <ActionCard
            key={item.key}
            icon={item.icon}
            title={item.title}
            detail={item.detail}
            busy={pending === item.key}
            disabled={action.isPending}
            onRun={() => action.mutate({ key: item.key, path: `semantic/${item.key}` })}
          />
        ))}
      </div>
      <ResultNotice result={action.data ?? null} error={action.error} />
    </div>
  );
}

function ActionCard({
  icon: Icon,
  title,
  detail,
  busy,
  disabled,
  onRun,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  detail: string;
  busy: boolean;
  disabled: boolean;
  onRun: () => void;
}) {
  return (
    <Card>
      <CardContent className="flex h-full flex-col gap-3 pt-5">
        <div className="flex items-start gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Icon className="size-4" />
          </span>
          <div>
            <CardTitle className="text-sm">{title}</CardTitle>
            <CardDescription className="mt-1">{detail}</CardDescription>
          </div>
        </div>
        <div className="mt-auto">
          <Button size="sm" variant="secondary" disabled={disabled} onClick={onRun}>
            {busy ? <Loader2 className="animate-spin" /> : <RefreshCw />}
            {busy ? "Running…" : "Run"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// --- 6. Audit Center ---------------------------------------------------------------

const AUDIT_FILTERS: Array<{ id: string | null; label: string }> = [
  { id: null, label: "All" },
  { id: "logins", label: "User logins" },
  { id: "logouts", label: "User logouts" },
  { id: "llm", label: "LLM changes" },
  { id: "dq", label: "DQ refreshes" },
  { id: "catalog", label: "Catalog refreshes" },
  { id: "graph", label: "Graph refreshes" },
];

export function AuditCenterPanel() {
  const [category, setCategory] = React.useState<string | null>(null);
  const audit = useAudit(category);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Audit filters">
        {AUDIT_FILTERS.map((filter) => {
          const count = filter.id ? audit.data?.counts[filter.id] : undefined;
          return (
            <button
              key={filter.label}
              type="button"
              aria-pressed={category === filter.id}
              onClick={() => setCategory(filter.id)}
              className={cn(
                "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                category === filter.id
                  ? "border-primary/45 bg-primary/10 text-foreground"
                  : "border-border/60 text-muted-foreground hover:bg-muted/40",
              )}
            >
              {filter.label}
              {count != null ? <span className="ml-1.5 tabular-nums opacity-70">{count}</span> : null}
            </button>
          );
        })}
      </div>

      {audit.isPending ? (
        <LoadingState title="Loading audit log" size="sm" />
      ) : audit.isError || !audit.data ? (
        <Failed error={audit.error} />
      ) : audit.data.items.length ? (
        <Card>
          <CardContent className="overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead className="border-b border-border/70">
                <tr>
                  <th className={TABLE_HEAD}>Time</th>
                  <th className={TABLE_HEAD}>User</th>
                  <th className={TABLE_HEAD}>Action</th>
                  <th className={TABLE_HEAD}>Details</th>
                </tr>
              </thead>
              <tbody>
                {audit.data.items.map((item) => (
                  <tr key={item.id} className="border-b border-border/40 last:border-0">
                    <td className={cn(TABLE_CELL, "whitespace-nowrap text-muted-foreground")}>{when(item.createdAt)}</td>
                    <td className={cn(TABLE_CELL, "font-medium")}>{item.user ?? "—"}</td>
                    <td className={TABLE_CELL}>{item.action}</td>
                    <td className={cn(TABLE_CELL, "text-muted-foreground")}>{item.details ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      ) : (
        <EmptyState title="No audit entries yet" detail="Logins, LLM changes and refreshes are recorded here." />
      )}
    </div>
  );
}