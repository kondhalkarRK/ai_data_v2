"use client";

import type { SemanticPackResponse } from "@nql/shared-types";
import { Brain, Calculator, Gavel, Grid3x3, Layers3 } from "lucide-react";
import * as React from "react";

import { useCatalogEntities } from "@/hooks/use-entity-catalog";

import { AiUnderstanding, aiRowId, aiTabFor, type AiTab } from "./ai-understanding";
import { CoverageSummary } from "./coverage-summary";
import { DimensionsTable } from "./dimensions-section";
import { GovernanceRules } from "./governance-rules";
import { MeasuresTable } from "./measures-section";
import { RelationshipMatrix } from "./relationship-matrix";
import { buildSemanticLayer, type SearchHit } from "./semantic-layer";
import { SemanticSearch } from "./semantic-search";
import { Section } from "./ui";

type SectionId = "measures" | "dimensions" | "relationships" | "ai" | "governance";

function reveal(elementId: string) {
  window.setTimeout(() => {
    document.getElementById(elementId)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, 60);
}

export function BusinessSemanticExplorer({ pack }: { pack: SemanticPackResponse }) {
  const catalog = useCatalogEntities();
  const layer = React.useMemo(() => buildSemanticLayer(pack, catalog.data ?? []), [pack, catalog.data]);

  const [query, setQuery] = React.useState("");
  const [sections, setSections] = React.useState<Record<SectionId, boolean>>({
    measures: true,
    dimensions: true,
    relationships: true,
    ai: true,
    governance: false,
  });
  const [openMeasure, setOpenMeasure] = React.useState<string | null>(null);
  const [openDimension, setOpenDimension] = React.useState<string | null>(null);
  const [aiTab, setAiTab] = React.useState<AiTab>("concepts");
  const [aiFocus, setAiFocus] = React.useState<string | null>(null);

  const toggleSection = (id: SectionId) => setSections((current) => ({ ...current, [id]: !current[id] }));
  const openSection = (id: SectionId) => setSections((current) => ({ ...current, [id]: true }));

  function showMeasure(id: string) {
    openSection("measures");
    setOpenMeasure(id);
    reveal(`measure-${id}`);
  }

  function showDimension(id: string) {
    openSection("dimensions");
    setOpenDimension(id);
    reveal(`dimension-${id}`);
  }

  function pick(hit: SearchHit) {
    if (hit.section === "measures") showMeasure(hit.targetId);
    else if (hit.section === "dimensions") showDimension(hit.targetId);
    else {
      const row = layer.understanding.find((item) => item.key === hit.targetId);
      if (!row) return;
      openSection("ai");
      setAiTab(aiTabFor(row));
      setAiFocus(row.key);
      reveal(aiRowId(row.key));
    }
  }

  return (
    <div className="space-y-4">
      <CoverageSummary coverage={layer.coverage} />
      <SemanticSearch layer={layer} query={query} onQueryChange={setQuery} onPick={pick} />

      <Section
        id="semantic-measures"
        icon={Calculator}
        title="Business Measures"
        description="Every governed number the AI can calculate, how it is defined and what it can be sliced by."
        count={layer.measures.length + layer.derived.length}
        open={sections.measures}
        onToggle={() => toggleSection("measures")}
      >
        <MeasuresTable
          layer={layer}
          openId={openMeasure}
          onToggle={(id) => setOpenMeasure((current) => (current === id ? null : id))}
        />
      </Section>

      <Section
        id="semantic-dimensions"
        icon={Layers3}
        title="Business Dimensions"
        description="The ways business users slice and filter: their meaning, aliases and real example values."
        count={layer.dimensions.length}
        open={sections.dimensions}
        onToggle={() => toggleSection("dimensions")}
      >
        <DimensionsTable
          layer={layer}
          openId={openDimension}
          onToggle={(id) => setOpenDimension((current) => (current === id ? null : id))}
        />
      </Section>

      <Section
        id="semantic-relationships"
        icon={Grid3x3}
        title="Semantic Relationships"
        description="Which measures can be analysed by which dimensions through governed joins."
        count={layer.coverage.relationships}
        open={sections.relationships}
        onToggle={() => toggleSection("relationships")}
      >
        <RelationshipMatrix layer={layer} onPickMeasure={showMeasure} onPickDimension={showDimension} />
      </Section>

      <Section
        id="semantic-ai"
        icon={Brain}
        title="AI Understanding Layer"
        description="How everyday business language is translated into governed concepts before any SQL is written."
        count={layer.understanding.length}
        open={sections.ai}
        onToggle={() => toggleSection("ai")}
      >
        <AiUnderstanding
          layer={layer}
          tab={aiTab}
          onTabChange={(next) => {
            setAiTab(next);
            setAiFocus(null);
          }}
          focusKey={aiFocus}
        />
      </Section>

      <Section
        id="semantic-governance"
        icon={Gavel}
        title="Governance Rules"
        description={`Domain rules enforced on every AI answer · ${layer.domain} pack v${layer.version}`}
        count={layer.rules.always.length + layer.rules.never.length}
        open={sections.governance}
        onToggle={() => toggleSection("governance")}
      >
        <GovernanceRules rules={layer.rules} />
      </Section>
    </div>
  );
}
