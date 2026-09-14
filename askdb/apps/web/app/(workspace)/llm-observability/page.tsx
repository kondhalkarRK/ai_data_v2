"use client";

import { useQuery } from "@tanstack/react-query";
import { Info } from "lucide-react";
import { useMemo, useState } from "react";

import { LoadingState } from "@/components/loading/loading-state";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { PageShell } from "@/components/ui/page-shell";
import { useActiveIndustry } from "@/hooks/use-session";
import { apiClient } from "@/lib/api-client";
import { CHART_SERIES } from "@/lib/design";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui-store";

interface CostSummary {
  calls: number;
  totalTokens: number;
  estimatedCostUsd: number;
  avgCostPerQueryUsd: number;
  budgetUsd: number;
  budgetUsedPct: number;
  budgetWarning: boolean;
  byModel: Array<{ model: string; calls: number; tokens: number; costUsd: number }>;
  byDomain: Array<{ domain: string; calls: number; tokens: number; costUsd: number }>;
  spendOverTime: Array<{ date: string; costUsd: number }>;
  recent: Array<{
    id: string;
    model: string;
    purpose: string;
    totalTokens: number;
    estimatedCostUsd: number;
    createdAt: string;
    industry?: string | null;
  }>;
}

interface LlmControlsResponse {
  defaultModel: string;
  fallbackModel: string | null;
  defaultTemperature: number;
  monthlyBudgetUsd: number;
  models: Array<{
    id: string;
    label: string;
    supportsTopP: boolean;
    supportsTopK: boolean;
    typicalCostPerQueryUsd: number;
  }>;
  parameterHelp: {
    temperature: string;
    topP: string;
    topK: string;
  };
}

export default function LlmObservabilityPage() {
  const [tab, setTab] = useState<"cost" | "controls">("cost");

  return (
    <PageShell>
      <PageHeader
        title="LLM Observability"
        description="Token spend, budget posture, and sampling controls for SQL generation."
      />
      <div className="mb-5 inline-flex rounded-[var(--radius-control)] border border-border bg-muted/30 p-0.5 text-sm">
        {(
          [
            ["cost", "Cost Analytics"],
            ["controls", "LLM Controls"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={cn(
              "rounded-[var(--radius-control)] px-4 py-1.5",
              tab === id
                ? "bg-background font-medium text-foreground shadow-sm"
                : "text-muted-foreground",
            )}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "cost" ? <CostAnalyticsPanel /> : <LlmControlsPanel />}
    </PageShell>
  );
}

function CostAnalyticsPanel() {
  const industry = useActiveIndustry();
  const cost = useQuery({
    queryKey: ["cost", industry],
    queryFn: () => apiClient.get<CostSummary>("/api/v1/cost", { industry }),
  });

  if (cost.isPending) return <LoadingState title="Loading usage" />;
  if (cost.isError || !cost.data) {
    return (
      <Card>
        <CardContent className="pt-5 text-sm text-danger">
          Cost analytics require the analyst role and a migrated app database.
        </CardContent>
      </Card>
    );
  }

  const data = cost.data;
  const spendMax = Math.max(...data.spendOverTime.map((p) => p.costUsd), 0.0001);

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Calls" value={String(data.calls)} />
        <Metric label="Tokens" value={data.totalTokens.toLocaleString()} />
        <Metric label="Est. USD" value={`$${data.estimatedCostUsd.toFixed(4)}`} />
        <Metric label="Avg $/query" value={`$${data.avgCostPerQueryUsd.toFixed(4)}`} />
      </div>

      <Card
        className={cn(
          data.budgetWarning && "border-warning/50 bg-warning/5",
        )}
      >
        <CardContent className="pt-4">
          <div className="mb-2 flex items-center justify-between gap-2">
            <CardTitle className="text-sm">Monthly budget</CardTitle>
            <span className="text-xs tabular-nums text-muted-foreground">
              ${data.estimatedCostUsd.toFixed(4)} / ${data.budgetUsd.toFixed(2)}
            </span>
          </div>
          <div className="h-2 rounded-full bg-muted">
            <div
              className={cn(
                "h-2 rounded-full",
                data.budgetWarning ? "bg-warning" : "bg-primary",
              )}
              style={{ width: `${Math.min(data.budgetUsedPct, 100)}%` }}
            />
          </div>
          {data.budgetWarning ? (
            <p className="mt-2 text-xs text-warning">
              Usage is at or above 80% of the configured monthly budget.
            </p>
          ) : (
            <p className="mt-2 text-xs text-muted-foreground">
              {data.budgetUsedPct.toFixed(1)}% of budget used (recent window).
            </p>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardContent className="pt-4">
            <CardTitle className="mb-3 text-sm">Spend over time</CardTitle>
            {data.spendOverTime.length ? (
              <div className="flex h-36 items-end gap-1">
                {data.spendOverTime.slice(-30).map((point) => (
                  <div
                    key={point.date}
                    className="flex-1 rounded-t"
                    style={{
                      height: `${Math.max((point.costUsd / spendMax) * 100, 3)}%`,
                      backgroundColor: CHART_SERIES.primary,
                    }}
                    title={`${point.date}: $${point.costUsd.toFixed(4)}`}
                  />
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No billed LLM calls yet.</p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-3 pt-4">
            <CardTitle className="text-sm">Tokens by model</CardTitle>
            {data.byModel.map((row) => (
              <div key={row.model} className="text-sm">
                <div className="flex justify-between gap-2">
                  <span className="truncate font-medium">{row.model}</span>
                  <span className="tabular-nums text-muted-foreground">
                    {row.tokens.toLocaleString()} · ${row.costUsd.toFixed(4)}
                  </span>
                </div>
              </div>
            ))}
            {!data.byModel.length ? (
              <p className="text-sm text-muted-foreground">No model usage yet.</p>
            ) : null}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-3 pt-4">
            <CardTitle className="text-sm">Tokens by domain</CardTitle>
            {data.byDomain.map((row) => (
              <div key={row.domain} className="flex justify-between gap-2 text-sm">
                <span className="capitalize">{row.domain}</span>
                <span className="tabular-nums text-muted-foreground">
                  {row.tokens.toLocaleString()} · ${row.costUsd.toFixed(4)}
                </span>
              </div>
            ))}
            {!data.byDomain.length ? (
              <p className="text-sm text-muted-foreground">No domain usage yet.</p>
            ) : null}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-2 pt-4">
            <CardTitle className="text-sm">Recent calls</CardTitle>
            {data.recent.map((row) => (
              <div key={row.id} className="border-t border-border/60 py-2 text-sm">
                <p className="font-medium">
                  {row.model} · {row.purpose}
                </p>
                <CardDescription>
                  {row.totalTokens} tokens · ${row.estimatedCostUsd.toFixed(4)} ·{" "}
                  {new Date(row.createdAt).toLocaleString()}
                </CardDescription>
              </div>
            ))}
            {!data.recent.length ? (
              <p className="text-sm text-muted-foreground">
                No LLM usage yet. Template answers do not bill tokens.
              </p>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function LlmControlsPanel() {
  const industry = useActiveIndustry();
  const controls = useQuery({
    queryKey: ["llm-controls"],
    queryFn: () => apiClient.get<LlmControlsResponse>("/api/v1/llm/controls", { industry }),
  });
  const llmModel = useUiStore((s) => s.llmModel);
  const llmTemperature = useUiStore((s) => s.llmTemperature);
  const llmTopP = useUiStore((s) => s.llmTopP);
  const llmTopK = useUiStore((s) => s.llmTopK);
  const setLlmModel = useUiStore((s) => s.setLlmModel);
  const setLlmTemperature = useUiStore((s) => s.setLlmTemperature);
  const setLlmTopP = useUiStore((s) => s.setLlmTopP);
  const setLlmTopK = useUiStore((s) => s.setLlmTopK);

  const cost = useQuery({
    queryKey: ["cost", industry, "quota"],
    queryFn: () => apiClient.get<CostSummary>("/api/v1/cost", { industry }),
  });

  const selectedModel = useMemo(() => {
    const models = controls.data?.models ?? [];
    const id = llmModel || controls.data?.defaultModel;
    return models.find((m) => m.id === id) ?? models[0];
  }, [controls.data, llmModel]);

  const remainingQuestions = useMemo(() => {
    if (!cost.data || !selectedModel) return null;
    const remainingBudget = Math.max(cost.data.budgetUsd - cost.data.estimatedCostUsd, 0);
    const perQuery = selectedModel.typicalCostPerQueryUsd || cost.data.avgCostPerQueryUsd || 0.002;
    return Math.floor(remainingBudget / perQuery);
  }, [cost.data, selectedModel]);

  if (controls.isPending) return <LoadingState title="Loading LLM controls" />;
  if (controls.isError || !controls.data) {
    return (
      <Card>
        <CardContent className="pt-5 text-sm text-danger">
          LLM controls require the analyst role.
        </CardContent>
      </Card>
    );
  }

  const help = controls.data.parameterHelp;

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-4 pt-4">
          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="llm-model">
              Model
            </label>
            <select
              id="llm-model"
              className="w-full max-w-md rounded-[var(--radius-control)] border border-border bg-background px-3 py-2 text-sm"
              value={llmModel || controls.data.defaultModel}
              onChange={(event) => setLlmModel(event.target.value)}
            >
              {controls.data.models.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.label}
                </option>
              ))}
            </select>
            <p className="mt-2 text-xs text-muted-foreground">
              Catalog is sourced from server config (default
              {controls.data.fallbackModel ? " + fallback" : ""}).
              {remainingQuestions != null
                ? ` At current usage, you can ask approximately ${remainingQuestions.toLocaleString()} more questions this month with this model.`
                : ""}
            </p>
          </div>

          <ControlRow
            id="temperature"
            label="Temperature"
            help={help.temperature}
            value={llmTemperature}
            min={0}
            max={1.5}
            step={0.05}
            onChange={setLlmTemperature}
          />
          {llmTemperature > 0.7 ? (
            <p className="text-xs text-warning">
              Higher values may make SQL generation less consistent for repeated questions.
            </p>
          ) : null}

          <ControlRow
            id="top-p"
            label="Top-P"
            help={help.topP}
            value={llmTopP}
            min={0}
            max={1}
            step={0.05}
            onChange={setLlmTopP}
            disabled={!selectedModel?.supportsTopP}
          />

          <ControlRow
            id="top-k"
            label="Top-K"
            help={help.topK}
            value={llmTopK}
            min={1}
            max={200}
            step={1}
            onChange={setLlmTopK}
            disabled={!selectedModel?.supportsTopK}
          />
          {!selectedModel?.supportsTopK ? (
            <p className="text-xs text-muted-foreground">
              Top-K is disabled for the selected model because the provider does not support it.
            </p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

function ControlRow({
  id,
  label,
  help,
  value,
  min,
  max,
  step,
  onChange,
  disabled,
}: {
  id: string;
  label: string;
  help: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
  disabled?: boolean;
}) {
  return (
    <div className={cn(disabled && "opacity-50")}>
      <div className="mb-1 flex items-center gap-2">
        <label className="text-sm font-medium" htmlFor={id}>
          {label}
        </label>
        <span className="group relative inline-flex" title={help}>
          <Info className="size-3.5 text-muted-foreground" aria-label={help} />
          <span className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 hidden w-64 -translate-x-1/2 rounded-md bg-foreground px-2 py-1.5 text-[11px] leading-snug text-background group-hover:block">
            {help}
          </span>
        </span>
        <span className="ml-auto text-xs tabular-nums text-muted-foreground">{value}</span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(Number(event.target.value))}
        className="w-full max-w-md"
      />
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="pt-4">
        <CardDescription>{label}</CardDescription>
        <CardTitle className="mt-1 text-2xl tabular-nums">{value}</CardTitle>
      </CardContent>
    </Card>
  );
}
