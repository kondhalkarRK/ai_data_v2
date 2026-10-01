"use client";

import type { SemanticPackResponse } from "@nql/shared-types";
import { ChevronDown, ShieldCheck } from "lucide-react";
import * as React from "react";

import { useCatalogEntities } from "@/hooks/use-entity-catalog";

import { BusinessLanguage, languageRowId } from "./business-language";
import { GovernanceRules } from "./governance-rules";
import { MeasureCards } from "./measure-cards";
import { buildSemanticLayer, type SearchHit } from "./semantic-layer";
import { SemanticSearch } from "./semantic-search";
import { SliceCards } from "./slice-cards";
import { BlockHeader, panelClass } from "./ui";

function reveal(elementId: string) {
  window.setTimeout(() => {
    document.getElementById(elementId)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, 60);
}

export function BusinessSemanticExplorer({
  pack,
  initialQuery = "",
}: {
  pack: SemanticPackResponse;
  initialQuery?: string;
}) {
  const catalog = useCatalogEntities();
  const layer = React.useMemo(() => buildSemanticLayer(pack, catalog.data ?? []), [pack, catalog.data]);

  const [query, setQuery] = React.useState(initialQuery);
  const [openMeasure, setOpenMeasure] = React.useState<string | null>(null);
  const [openDimension, setOpenDimension] = React.useState<string | null>(null);
  const [showAllTerms, setShowAllTerms] = React.useState(false);
  const [termFocus, setTermFocus] = React.useState<string | null>(null);

  const ruleCount = layer.rules.always.length + layer.rules.never.length;
  const sliceCount = layer.dimensions.filter((dimension) => !dimension.synthetic).length;

  function pick(hit: SearchHit) {
    if (hit.section === "measures") {
      if (layer.measures.some((measure) => measure.id === hit.targetId)) {
        setOpenMeasure(hit.targetId);
        reveal(`measure-${hit.targetId}`);
      } else {
        reveal("semantic-measures");
      }
    } else if (hit.section === "dimensions") {
      setOpenDimension(hit.targetId);
      reveal(`dimension-${hit.targetId}`);
    } else {
      setShowAllTerms(true);
      setTermFocus(hit.targetId);
      reveal(languageRowId(hit.targetId));
    }
  }

  return (
    <div className="space-y-10">
      <div className="space-y-3">
        <SemanticSearch layer={layer} query={query} onQueryChange={setQuery} onPick={pick} />
        <p className="px-1 text-xs text-muted-foreground">
          The AI can calculate <span className="font-semibold text-foreground">{layer.measures.length} measures</span>,
          slice them <span className="font-semibold text-foreground">{sliceCount} ways</span>, and understands{" "}
          <span className="font-semibold text-foreground">{layer.understanding.length} business terms</span>.
        </p>
      </div>

      <section id="semantic-measures" className="scroll-mt-24 space-y-5">
        <BlockHeader
          title="What you can measure"
          description="Each governed number, what it means, and what it can be broken down by."
        />
        <MeasureCards
          layer={layer}
          openId={openMeasure}
          onToggle={(id) => setOpenMeasure((current) => (current === id ? null : id))}
        />
      </section>

      <section id="semantic-dimensions" className="scroll-mt-24 space-y-5">
        <BlockHeader
          title="Ways to slice the business"
          description="The views people use to group and filter numbers, with real example values."
        />
        <SliceCards
          layer={layer}
          openId={openDimension}
          onToggle={(id) => setOpenDimension((current) => (current === id ? null : id))}
        />
      </section>

      <section id="semantic-language" className="scroll-mt-24 space-y-5">
        <BlockHeader
          title="Business language the AI understands"
          description="Everyday words and how they are translated before any query runs. Ambiguous words trigger a clarifying question."
        />
        <BusinessLanguage
          rows={layer.understanding}
          showAll={showAllTerms}
          onShowAll={() => setShowAllTerms(true)}
          focusKey={termFocus}
        />
      </section>

      {ruleCount ? (
        <details className={`group ${panelClass}`}>
          <summary className="flex cursor-pointer list-none items-center gap-3 px-5 py-4 [&::-webkit-details-marker]:hidden">
            <ShieldCheck className="size-4 text-success" />
            <span className="flex-1">
              <span className="block text-[15px] font-semibold text-foreground">Rules the AI always follows</span>
              <span className="block text-xs text-muted-foreground">
                {ruleCount} governance rules applied to every answer · {layer.domain} pack v{layer.version}
              </span>
            </span>
            <ChevronDown className="size-4 text-muted-foreground transition-transform group-open:rotate-180" />
          </summary>
          <div className="border-t border-border/60 p-5">
            <GovernanceRules rules={layer.rules} />
          </div>
        </details>
      ) : null}
    </div>
  );
}
