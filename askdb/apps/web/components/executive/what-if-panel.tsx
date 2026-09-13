"use client";

import * as React from "react";

import type { WhatIfPreset } from "@/components/executive/types";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api-client";
import { useActiveIndustry } from "@/hooks/use-session";
import { cn } from "@/lib/utils";

interface ScenarioResult {
  available: boolean;
  message: string;
  actual?: number | null;
  scenario?: number | null;
  delta?: number | null;
  narrative?: string | null;
}

export function WhatIfPanel({ presets }: { presets: WhatIfPreset[] }) {
  const industry = useActiveIndustry();
  const [selected, setSelected] = React.useState(presets.find((p) => p.supported)?.id ?? "");
  const [customPct, setCustomPct] = React.useState(5);
  const [result, setResult] = React.useState<ScenarioResult | null>(null);
  const [busy, setBusy] = React.useState(false);

  const active = presets.find((p) => p.id === selected) ?? presets[0];

  async function run(preset?: WhatIfPreset) {
    const target = preset ?? active;
    if (!target) return;
    if (!target.supported) {
      setResult({
        available: false,
        message:
          target.unsupportedReason ||
          "This scenario can't be calculated from currently available metrics.",
      });
      return;
    }
    setBusy(true);
    try {
      const response = await apiClient.post<ScenarioResult>(
        "/api/v1/kpis/scenario",
        {
          metric: target.metric,
          changeType: "percent",
          changeValue: preset ? target.changeValue : customPct,
          direction: target.direction,
        },
        { industry },
      );
      setResult(response);
    } catch {
      setResult({
        available: false,
        message: "This scenario can't be calculated from currently available metrics.",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-2xl border border-border/70 bg-background p-4 shadow-sm">
      <div className="mb-3">
        <h2 className="text-sm font-semibold tracking-tight">What-If Analysis</h2>
        <p className="text-xs text-muted-foreground">
          Current reality vs simulated scenario — no forecasts, no invented metrics.
        </p>
      </div>

      <div className="mb-3 flex flex-wrap gap-2">
        {presets.map((preset) => (
          <button
            key={preset.id}
            type="button"
            className={cn(
              "rounded-full border px-3 py-1.5 text-xs",
              selected === preset.id
                ? "border-foreground bg-foreground text-background"
                : "border-border/70 text-muted-foreground hover:text-foreground",
              !preset.supported && "opacity-50",
            )}
            onClick={() => {
              setSelected(preset.id);
              setResult(null);
              if (!preset.supported) {
                setResult({
                  available: false,
                  message:
                    preset.unsupportedReason ||
                    "This scenario can't be calculated from currently available metrics.",
                });
              }
            }}
          >
            {preset.label}
          </button>
        ))}
      </div>

      {active?.supported ? (
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-muted-foreground">
            Change %
            <input
              type="number"
              min={0}
              className="h-9 w-24 rounded-lg border border-border bg-background px-2 text-sm text-foreground"
              value={customPct}
              onChange={(event) => setCustomPct(Number(event.target.value))}
            />
          </label>
          <Button type="button" size="sm" disabled={busy} onClick={() => void run()}>
            Run scenario
          </Button>
        </div>
      ) : null}

      {result ? (
        <div className="mt-4 rounded-xl border border-border/60 bg-muted/20 p-3">
          {result.available && result.actual != null && result.scenario != null ? (
            <div className="grid gap-3 sm:grid-cols-3">
              <div>
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Current</p>
                <p className="text-lg font-semibold tabular-nums">
                  {result.actual.toLocaleString()}
                </p>
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Scenario</p>
                <p className="text-lg font-semibold tabular-nums">
                  {result.scenario.toLocaleString()}
                </p>
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  Estimated impact
                </p>
                <p className="text-lg font-semibold tabular-nums">
                  {(result.delta ?? 0) >= 0 ? "+" : ""}
                  {(result.delta ?? 0).toLocaleString()}
                </p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{result.message}</p>
          )}
          {result.narrative ? (
            <p className="mt-2 text-xs text-muted-foreground">{result.narrative}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
