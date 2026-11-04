"use client";

import type { SemanticPackResponse } from "@nql/shared-types";
import * as React from "react";

import { AnalyticsBuilderShell } from "@/components/analytics-builder/analytics-builder-shell";
import { AskWiz } from "@/components/analytics-builder/askwiz";
import { useActiveIndustry, useSession } from "@/hooks/use-session";

export function BuilderModes({ pack }: { pack: SemanticPackResponse }) {
  const industry = useActiveIndustry();
  const { data: user } = useSession();
  const enabled = (process.env.NEXT_PUBLIC_ASK_ME_ASKWIZ_ENABLED ?? "true").toLowerCase() === "true";
  if (industry !== "automotive" || !enabled) return <AnalyticsBuilderShell key={industry} pack={pack} />;
  // Remount both workspaces when identity/access changes, never retain another scope's results.
  const scope = JSON.stringify([user?.id, user?.role, user?.regionAccess]);
  return <AutomotiveModes key={scope} pack={pack} />;
}

function AutomotiveModes({ pack }: { pack: SemanticPackResponse }) {
  const [mode, setMode] = React.useState<"custom" | "auto">("custom");
  const [visited, setVisited] = React.useState(false);
  return <div className="space-y-5">
    <div role="group" aria-label="Analytics Builder mode" className="inline-flex rounded-xl border border-border bg-surface-raised p-1">
      {(["custom", "auto"] as const).map((value) => <button key={value} type="button" aria-pressed={mode === value} onClick={() => { setMode(value); if (value === "auto") setVisited(true); }} className={`rounded-lg px-5 py-2 text-sm font-medium focus-visible:outline-ring ${mode === value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>{value === "auto" ? "Auto · AskWiz" : "Custom"}</button>)}
    </div>
    <div hidden={mode !== "custom"}><AnalyticsBuilderShell pack={pack} /></div>
    {visited ? <div hidden={mode !== "auto"}><AskWiz /></div> : null}
  </div>;
}
