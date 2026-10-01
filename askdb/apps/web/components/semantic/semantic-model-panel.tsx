"use client";

import type { SemanticPackResponse } from "@nql/shared-types";
import { BriefcaseBusiness, Code2 } from "lucide-react";
import * as React from "react";

import { BusinessSemanticExplorer } from "@/components/semantic/business/business-semantic-explorer";
import { SegmentedTabs } from "@/components/semantic/business/ui";
import { TechnicalModelView } from "@/components/semantic/technical-model-view";

type ModelView = "business" | "technical";

export function SemanticModelPanel({ pack }: { pack: SemanticPackResponse }) {
  const [view, setView] = React.useState<ModelView>("business");
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-foreground">
            {view === "business" ? "Business Metrics Catalog & AI Semantic Layer" : "Physical model contracts"}
          </h2>
          <p className="text-xs text-muted-foreground">
            {view === "business"
              ? "What each number means, how it is calculated, and how the AI understands business language."
              : "Tables, columns, keys and join contracts behind the business layer."}
          </p>
        </div>
        <SegmentedTabs
          value={view}
          onChange={setView}
          ariaLabel="Semantic model view"
          size="md"
          options={[
            { value: "business", label: "Business Semantic View", icon: BriefcaseBusiness },
            { value: "technical", label: "Technical View", icon: Code2 },
          ]}
        />
      </div>
      {view === "business" ? <BusinessSemanticExplorer pack={pack} /> : <TechnicalModelView pack={pack} />}
    </div>
  );
}
