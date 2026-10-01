"use client";

import type { SemanticPackResponse } from "@nql/shared-types";
import { BriefcaseBusiness, Code2 } from "lucide-react";
import * as React from "react";

import { BusinessSemanticExplorer } from "@/components/semantic/business/business-semantic-explorer";
import { SegmentedTabs } from "@/components/semantic/business/ui";
import { TechnicalModelView } from "@/components/semantic/technical-model-view";

type ModelView = "business" | "technical";

export function SemanticModelPanel({ pack, initialQuery }: { pack: SemanticPackResponse; initialQuery?: string }) {
  const [view, setView] = React.useState<ModelView>("business");
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-foreground">
            {view === "business" ? "What the AI knows about your business" : "Physical model contracts"}
          </h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {view === "business"
              ? "The governed measures, views and vocabulary every AI answer is built on."
              : "Tables, columns, keys and join contracts behind the business layer."}
          </p>
        </div>
        <SegmentedTabs
          value={view}
          onChange={setView}
          ariaLabel="Semantic model view"
          size="md"
          options={[
            { value: "business", label: "Business view", icon: BriefcaseBusiness },
            { value: "technical", label: "Technical view", icon: Code2 },
          ]}
        />
      </div>
      {view === "business" ? (
        <BusinessSemanticExplorer pack={pack} initialQuery={initialQuery} />
      ) : (
        <TechnicalModelView pack={pack} />
      )}
    </div>
  );
}
