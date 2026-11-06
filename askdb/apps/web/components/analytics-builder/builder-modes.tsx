"use client";

import type { SemanticPackResponse } from "@nql/shared-types";
import * as React from "react";

import { AnalyticsBuilderShell } from "@/components/analytics-builder/analytics-builder-shell";
import { AskWiz } from "@/components/analytics-builder/askwiz";
import { AnalyticsWorkspace } from "@/components/analytics-builder/analytics-workspace";
import { AskBI } from "@/components/analytics-builder/askbi/askbi";
import { useActiveIndustry, useSession } from "@/hooks/use-session";

export function BuilderModes({ pack }: { pack: SemanticPackResponse }) {
  const industry = useActiveIndustry();
  const { data: user } = useSession();
  const askbi = (process.env.NEXT_PUBLIC_ASK_ME_ASKBI_ENABLED ?? "false").toLowerCase() === "true";
  if (industry === "automotive" && askbi) return <AutomotiveModes key={JSON.stringify([user?.id, user?.role, user?.regionAccess, "askbi"])} pack={pack} askbi />;
  const unified = (process.env.NEXT_PUBLIC_ASK_ME_ANALYTICS_WORKSPACE_ENABLED ?? "false").toLowerCase() === "true";
  if (industry === "automotive" && unified) return <AnalyticsWorkspace key={JSON.stringify([user?.id, user?.role, user?.regionAccess])} pack={pack} />;
  const enabled = (process.env.NEXT_PUBLIC_ASK_ME_ASKWIZ_ENABLED ?? "true").toLowerCase() === "true";
  if (industry !== "automotive" || !enabled) return <AnalyticsBuilderShell key={industry} pack={pack} />;
  // Remount both workspaces when identity/access changes, never retain another scope's results.
  const scope = JSON.stringify([user?.id, user?.role, user?.regionAccess]);
  return <AutomotiveModes key={scope} pack={pack} />;
}

function AutomotiveModes({ pack, askbi = false }: { pack: SemanticPackResponse; askbi?: boolean }) {
  const [mode, setMode] = React.useState<"custom" | "auto">("custom");
  const [visited, setVisited] = React.useState(false);
  const requestedAuto = React.useSyncExternalStore(
    () => () => {},
    () => askbi && new URLSearchParams(window.location.search).has("askbiReport"),
    () => false,
  );
  const activeMode = requestedAuto && !visited ? "auto" : mode;
  return <div className="space-y-5">
    <div role="group" aria-label="Analytics Builder mode" className="inline-flex rounded-xl border border-border bg-surface-raised p-1">
      {(["custom", "auto"] as const).map((value) => <button key={value} type="button" aria-pressed={activeMode === value} onClick={() => { setMode(value); setVisited(true); }} className={`rounded-lg px-5 py-2 text-sm font-medium focus-visible:outline-ring ${activeMode === value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>{value === "auto" ? askbi ? "Auto Report · AskBI" : "Auto · AskWiz" : askbi ? "Custom Report" : "Custom"}</button>)}
    </div>
    <div hidden={activeMode !== "custom"}><AnalyticsBuilderShell pack={pack} /></div>
    {visited || requestedAuto ? <div hidden={activeMode !== "auto"}>{askbi ? <AskBI /> : <AskWiz />}</div> : null}
  </div>;
}
