"use client";

import { BookOpenText, Boxes, Network } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { LoadingState } from "@/components/loading/loading-state";
import { OntologyBrowser } from "@/components/ontology/ontology-browser";
import { GlossaryCatalog } from "@/components/semantic/glossary-catalog";
import { SemanticModelPanel } from "@/components/semantic/semantic-model-panel";
import { IndustrySwitcher } from "@/components/shell/industry-switcher";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { useOntologySnapshot, useSemanticPack } from "@/hooks/use-semantic";
import { cn } from "@/lib/utils";

const TABS = [
  { id: "glossary", label: "Business Glossary", icon: BookOpenText },
  { id: "model", label: "Semantic Model", icon: Boxes },
  { id: "graph", label: "Knowledge Graph", icon: Network },
] as const;

export type AtlasTab = (typeof TABS)[number]["id"];

function tabFromPath(pathname: string): AtlasTab | null {
  if (pathname.includes("/glossary")) return "glossary";
  if (pathname.includes("/models")) return "model";
  if (pathname.includes("/ontology")) return "graph";
  return null;
}

export function SemanticAtlasShell({ initialTab }: { initialTab?: AtlasTab }) {
  return (
    <Suspense fallback={<LoadingState title="Opening Semantic Atlas" size="lg" />}>
      <SemanticAtlasInner initialTab={initialTab} />
    </Suspense>
  );
}

function SemanticAtlasInner({ initialTab }: { initialTab?: AtlasTab }) {
  const pack = useSemanticPack();
  const snapshot = useOntologySnapshot();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const requested = (searchParams.get("tab") as AtlasTab | null) || initialTab || tabFromPath(pathname);
  const tab: AtlasTab = TABS.some((item) => item.id === requested) ? (requested as AtlasTab) : "glossary";
  const glossaryQuery = searchParams.get("q") ?? "";
  const focus = searchParams.get("focus");

  function selectTab(next: AtlasTab) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", next);
    if (next !== "glossary") params.delete("q");
    if (next !== "graph") params.delete("focus");
    router.replace(`/semantic?${params.toString()}`, { scroll: false });
  }

  const graphFirst = tab === "graph";

  return (
    <div
      className={cn(
        graphFirst &&
          "flex h-[calc(100dvh-var(--topbar-height)-2rem)] min-h-0 flex-col overflow-hidden lg:h-[calc(100dvh-var(--topbar-height)-3rem)]",
      )}
    >
      {graphFirst ? (
        <div className="mb-2 flex shrink-0 items-center gap-2 overflow-x-auto">
          <h1 className="shrink-0 text-base font-semibold tracking-tight text-foreground">
            Semantic Atlas
          </h1>
          <IndustrySwitcher />
          <AtlasTabs tab={tab} onSelect={selectTab} compact />
        </div>
      ) : (
        <PageHeader
          title="Semantic Atlas"
          description="Governed catalog of business language, model contracts, and the knowledge graph."
        />
      )}

      {pack.isPending ? (
        <LoadingState title="Loading semantic pack" size="sm" />
      ) : pack.isError || !pack.data ? (
        <Card>
          <CardContent className="pt-5 text-sm text-danger">
            The active semantic pack could not be loaded.
          </CardContent>
        </Card>
      ) : graphFirst ? (
        <>
          <div className="min-h-0 flex-1">
            {snapshot.isPending ? (
              <LoadingState title="Building semantic relationships" size="lg" />
            ) : snapshot.isError || !snapshot.data ? (
              <p className="text-sm text-danger">The knowledge graph could not be loaded.</p>
            ) : (
              <OntologyBrowser snapshot={snapshot.data} initialFocusId={focus} />
            )}
          </div>
        </>
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="rounded-full border border-border bg-surface-raised px-2.5 py-1 font-medium text-foreground">
              {pack.data.summary.label}
            </span>
            <span>{pack.data.summary.tableCount} tables</span>
            <span aria-hidden="true">·</span>
            <span>{pack.data.summary.measureCount} measures</span>
            <span aria-hidden="true">·</span>
            <span>{pack.data.summary.glossaryTermCount} glossary terms</span>
          </div>

          <AtlasTabs tab={tab} onSelect={selectTab} />

          {tab === "glossary" ? (
            <GlossaryCatalog pack={pack.data} initialQuery={glossaryQuery} />
          ) : null}
          {tab === "model" ? <SemanticModelPanel pack={pack.data} /> : null}
        </>
      )}
    </div>
  );
}

function AtlasTabs({
  tab,
  onSelect,
  compact = false,
}: {
  tab: AtlasTab;
  onSelect: (next: AtlasTab) => void;
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        compact
          ? "ml-auto flex shrink-0 gap-1"
          : "mb-4 grid grid-cols-1 gap-2 sm:grid-cols-3",
      )}
      role="tablist"
      aria-label="Semantic Atlas"
    >
      {TABS.map((item) => {
        const Icon = item.icon;
        const active = tab === item.id;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={active}
            className={cn(
              compact
                ? "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium"
                : "flex h-14 items-center justify-center gap-2 rounded-2xl border text-sm font-semibold shadow-sm",
              active
                ? "border-primary/45 bg-primary/10 text-foreground"
                : "border-border/60 bg-surface-raised/80 text-muted-foreground hover:bg-muted/40",
            )}
            onClick={() => onSelect(item.id)}
          >
            <Icon className={compact ? "size-3.5" : "size-4"} />
            <span className={compact ? "hidden sm:inline" : undefined}>{item.label}</span>
          </button>
        );
      })}
    </div>
  );
}
