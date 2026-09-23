"use client";

import type { OntologySnapshot } from "@nql/shared-types";
import {
  Background,
  Controls,
  MiniMap,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type NodeTypes,
  type EdgeTypes,
} from "@xyflow/react";
import { motion } from "framer-motion";
import { Orbit, Share2, Sparkles } from "lucide-react";
import * as React from "react";

import { ClusterLayer } from "@/components/ontology/cluster-layer";
import { GalaxyEdge, EDGE_STYLES, type GalaxyFlowEdge } from "@/components/ontology/galaxy-edge";
import { GalaxyNode, type GalaxyFlowNode } from "@/components/ontology/galaxy-node";
import "@/components/ontology/galaxy-styles.css";
import { NodeDrawer } from "@/components/ontology/node-drawer";
import { ParticleField } from "@/components/ontology/particle-field";
import { Button } from "@/components/ui/button";
import {
  JOURNEYS,
  deriveAssetContext,
  displayName,
  journeyNodeIds,
  storyLabel,
  type ContextOverlay,
} from "@/lib/ontology/asset-context";
import { hopNeighborhood } from "@/lib/ontology/graph-metrics";
import {
  ONTOLOGY_KIND_FILTERS,
  nodeMatchesKindFilter,
  nodeMatchesKindFilters,
  type OntologyKindFilter,
} from "@/lib/ontology/kind-filter";
import {
  edgeVisualKind,
  layoutGalaxy,
  type CentralityMetric,
  type GalaxyMode,
  type PositionedNode,
} from "@/lib/ontology/layouts";
import { conceptOnlySnapshot, mergeOntologyConcepts, withoutDomainNodes } from "@/lib/ontology/merge-concepts";
import { cn } from "@/lib/utils";

const nodeTypes: NodeTypes = { galaxy: GalaxyNode };
const edgeTypes: EdgeTypes = { galaxy: GalaxyEdge };

const MODES: ReadonlyArray<{
  id: GalaxyMode;
  label: string;
  hint: string;
  icon: React.ComponentType<{ className?: string }>;
}> = [
  {
    id: "semantic",
    label: "Knowledge Graph",
    hint: "Organic semantic network. One node per business concept, linked by named relationships.",
    icon: Sparkles,
  },
  {
    id: "network",
    label: "Relationship Network",
    hint: "Investigative view. Size and pull show influence and hidden communities.",
    icon: Share2,
  },
  {
    id: "ontology",
    label: "Concept Graph",
    hint: "Business vocabulary as a radial taxonomy — meaning, not tables.",
    icon: Orbit,
  },
];

const METRICS: ReadonlyArray<{ id: CentralityMetric; label: string; hint: string }> = [
  { id: "degree", label: "Degree", hint: "How many direct connections an asset has." },
  { id: "betweenness", label: "Betweenness", hint: "How often an asset sits on the shortest path between others." },
  { id: "pagerank", label: "PageRank", hint: "How influential an asset is based on what links to it." },
];

const OVERLAYS: ReadonlyArray<{ id: ContextOverlay; label: string; hint: string }> = [
  {
    id: "business",
    label: "Business",
    hint: "Everyday names, KPIs, and glossary language.",
  },
  {
    id: "technical",
    label: "Technical",
    hint: "Table names, columns, and join keys.",
  },
  {
    id: "governance",
    label: "Governance",
    hint: "Owners, stewardship, and relationship types.",
  },
];

const KIND_PILL_ORDER: OntologyKindFilter[] = [
  "all",
  "entity",
  "fact",
  "measure",
  "dimension",
  "relationship",
];

const KIND_PILL_LABEL: Record<OntologyKindFilter, string> = {
  all: "All",
  entity: "Actor",
  fact: "Event",
  measure: "Outcome",
  dimension: "Attribute",
  relationship: "Connected",
};

export function OntologyBrowser({
  snapshot,
  initialFocusId,
}: {
  snapshot: OntologySnapshot;
  initialFocusId?: string | null;
}) {
  return (
    <ReactFlowProvider>
      <OntologyBrowserInner snapshot={snapshot} initialFocusId={initialFocusId} />
    </ReactFlowProvider>
  );
}

function OntologyBrowserInner({
  snapshot,
  initialFocusId,
}: {
  snapshot: OntologySnapshot;
  initialFocusId?: string | null;
}) {
  const { fitView, setCenter, getNode } = useReactFlow();
  const [mode, setMode] = React.useState<GalaxyMode>("semantic");
  const [metric, setMetric] = React.useState<CentralityMetric>("pagerank");
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [pulseId, setPulseId] = React.useState<string | null>(null);
  const [activeCluster, setActiveCluster] = React.useState<string | null>(null);
  const [showClusters, setShowClusters] = React.useState(true);
  const [motionEnabled, setMotionEnabled] = React.useState(true);
  const [kindFilters, setKindFilters] = React.useState<OntologyKindFilter[]>(["all"]);
  const [overlay, setOverlay] = React.useState<ContextOverlay>("business");
  const [journeyId, setJourneyId] = React.useState<string | null>(null);

  const graph = React.useMemo(() => {
    const merged = withoutDomainNodes(mergeOntologyConcepts(snapshot));
    return mode === "ontology" ? conceptOnlySnapshot(merged) : merged;
  }, [snapshot, mode]);

  const positioned = React.useMemo(
    () => layoutGalaxy(graph, mode, metric),
    [graph, mode, metric],
  );

  const nodeById = React.useMemo(() => {
    const map = new Map(graph.nodes.map((node) => [node.id, node]));
    return map;
  }, [graph.nodes]);

  const journeyPath = React.useMemo(() => {
    const journey = JOURNEYS.find((item) => item.id === journeyId);
    return journey ? journeyNodeIds(graph, journey.seeds) : [];
  }, [journeyId, graph]);

  const journeySet = React.useMemo(() => new Set(journeyPath), [journeyPath]);

  const focus = React.useMemo(() => {
    if (!selectedId) return null;
    const links = graph.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
    }));
    const one = hopNeighborhood(selectedId, links, 1);
    const two = hopNeighborhood(selectedId, links, 2);
    return { one, two };
  }, [selectedId, graph.edges]);

  const flowNodes: GalaxyFlowNode[] = React.useMemo(() => {
    return positioned.map((node) => {
      const size = Math.max(36, node.radius * 2) + 24;
      let dimmed = false;
      let focused = false;
      let hop: 0 | 1 | 2 | null = null;
      if (focus) {
        if (node.id === selectedId) {
          focused = true;
          hop = 0;
        } else if (focus.one.nodes.has(node.id)) {
          hop = 1;
        } else if (focus.two.nodes.has(node.id)) {
          hop = 2;
          dimmed = false;
        } else {
          dimmed = true;
        }
      }
      if (activeCluster && node.cluster !== activeCluster && node.id !== selectedId) {
        dimmed = true;
      }
      if (!nodeMatchesKindFilters(node, kindFilters)) {
        dimmed = true;
        if (node.id !== selectedId) focused = false;
      } else if (!kindFilters.includes("all") && !focus) {
        focused = true;
      }
      if (journeySet.size && !journeySet.has(node.id) && node.id !== selectedId) {
        dimmed = true;
      }
      if (journeySet.has(node.id) && !focus) {
        focused = true;
      }
      const asset = nodeById.get(node.id);
      const badges = asset ? deriveAssetContext(asset, graph).badges : [];
      return {
        id: node.id,
        type: "galaxy",
        position: { x: node.x - size / 2, y: node.y - size / 2 },
        data: {
          ...node,
          dimmed,
          focused,
          pulsing: pulseId === node.id,
          hop,
          motionEnabled,
          displayLabel: asset ? displayName(asset, overlay) : node.label,
          certified: badges.includes("certified") || badges.includes("trusted"),
          review: badges.includes("review"),
        },
        style: { width: size, height: size + 4 },
        zIndex: focused || pulseId === node.id ? 20 : dimmed ? 1 : 5,
      };
    });
  }, [
    positioned,
    focus,
    selectedId,
    pulseId,
    activeCluster,
    kindFilters,
    motionEnabled,
    journeySet,
    nodeById,
    overlay,
    graph,
  ]);

  const flowEdges: GalaxyFlowEdge[] = React.useMemo(() => {
    return graph.edges.map((edge) => {
      const visualKind = edgeVisualKind(edge, nodeById);
      let dimmed = false;
      let emphasized = false;
      if (focus) {
        emphasized = focus.two.edges.has(edge.id);
        dimmed = !emphasized;
        if (focus.one.edges.has(edge.id)) emphasized = true;
      }
      if (activeCluster) {
        const source = nodeById.get(edge.source);
        const target = nodeById.get(edge.target);
        if (source?.cluster !== activeCluster && target?.cluster !== activeCluster) {
          dimmed = true;
          emphasized = false;
        }
      }
      if (!kindFilters.includes("all")) {
        const source = nodeById.get(edge.source);
        const target = nodeById.get(edge.target);
        const onlyConnected = kindFilters.length === 1 && kindFilters[0] === "relationship";
        if (onlyConnected) {
          emphasized = !dimmed;
        } else {
          const sourceMatch = source ? nodeMatchesKindFilters(source, kindFilters) : false;
          const targetMatch = target ? nodeMatchesKindFilters(target, kindFilters) : false;
          if (!sourceMatch && !targetMatch) {
            dimmed = true;
            emphasized = false;
          } else if (!focus) {
            emphasized = sourceMatch || targetMatch;
          }
        }
      }
      if (journeySet.size) {
        if (journeySet.has(edge.source) && journeySet.has(edge.target)) {
          emphasized = true;
          dimmed = false;
        } else if (!focus) {
          dimmed = true;
          emphasized = false;
        }
      }
      return {
        id: edge.id,
        type: "galaxy",
        source: edge.source,
        target: edge.target,
        data: {
          visualKind,
          label: storyLabel(edge, overlay) || EDGE_STYLES[visualKind].label,
          dimmed,
          emphasized,
          motionEnabled,
        },
        animated: motionEnabled && (emphasized || EDGE_STYLES[visualKind].animated) && !dimmed,
        zIndex: emphasized ? 4 : 0,
      };
    });
  }, [graph.edges, nodeById, focus, activeCluster, kindFilters, motionEnabled, journeySet, overlay]);

  const selectedNode = selectedId ? (nodeById.get(selectedId) ?? null) : null;

  const relationshipCount = focus?.one.edges.size ?? 0;

  const kindCounts = React.useMemo(() => {
    const counts = {} as Record<OntologyKindFilter, number>;
    for (const filter of ONTOLOGY_KIND_FILTERS) {
      counts[filter.id] =
        filter.id === "all"
          ? graph.nodes.length
          : graph.nodes.filter((node) => nodeMatchesKindFilter(node, filter.id)).length;
    }
    return counts;
  }, [graph.nodes]);

  function toggleKind(id: OntologyKindFilter) {
    setKindFilters((current) => {
      if (id === "all") return ["all"];
      const withoutAll = current.filter((item) => item !== "all");
      const next = withoutAll.includes(id)
        ? withoutAll.filter((item) => item !== id)
        : [...withoutAll, id];
      return next.length ? next : ["all"];
    });
  }

  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      void fitView({ padding: 0.08, duration: 450 });
    }, 40);
    return () => window.clearTimeout(timer);
  }, [mode, metric, graph, fitView]);

  const focusNode = React.useCallback(
    (nodeId: string) => {
      setSelectedId(nodeId);
      setPulseId(nodeId);
      window.setTimeout(() => setPulseId(null), 2400);
      requestAnimationFrame(() => {
        const rfNode = getNode(nodeId);
        if (!rfNode) return;
        const width = Number(rfNode.style?.width ?? 80);
        const height = Number(rfNode.style?.height ?? 80);
        void setCenter(rfNode.position.x + width / 2, rfNode.position.y + height / 2, {
          zoom: 1.35,
          duration: 700,
        });
      });
    },
    [getNode, setCenter],
  );

  React.useEffect(() => {
    if (!initialFocusId) return;
    const match =
      graph.nodes.find((node) => node.id === initialFocusId) ??
      graph.nodes.find(
        (node) =>
          node.id.toLowerCase().includes(initialFocusId.toLowerCase()) ||
          node.label.toLowerCase().includes(initialFocusId.toLowerCase()),
      );
    if (!match) return;
    const timer = window.setTimeout(() => focusNode(match.id), 500);
    return () => window.clearTimeout(timer);
  }, [initialFocusId, graph.nodes, focusNode]);

  const positionedForClusters: PositionedNode[] = positioned;

  function selectJourney(next: string | null) {
    setJourneyId(next);
    if (!next) return;
    const journey = JOURNEYS.find((item) => item.id === next);
    if (!journey) return;
    const ids = journeyNodeIds(graph, journey.seeds);
    if (ids[0]) focusNode(ids[0]);
  }

  return (
    <div
      className="semantic-galaxy relative flex h-full min-h-0 w-full flex-col"
      data-motion={motionEnabled ? "on" : "off"}
      data-mode={mode}
    >
      {motionEnabled ? <ParticleField /> : null}

      <div className="galaxy-toolbar relative z-20 flex shrink-0 items-center gap-2 overflow-x-auto px-2 py-1.5">
        <div className="flex shrink-0 items-center gap-1" role="tablist" aria-label="Graph type">
          {MODES.map((item) => {
            const Icon = item.icon;
            const active = mode === item.id;
            return (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={active}
                aria-label={`${item.label}. ${item.hint}`}
                data-hint={item.hint}
                className={cn(
                  "galaxy-chip galaxy-hint inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors",
                  active
                    ? "border-primary/40 bg-primary/15 text-foreground"
                    : "border-transparent text-muted-foreground hover:bg-muted/40 hover:text-foreground",
                )}
                data-active={active}
                onClick={() => setMode(item.id)}
              >
                <Icon className="size-3" />
                {item.label}
              </button>
            );
          })}
        </div>

        <ToolbarDivider />

        <div
          className="flex shrink-0 items-center gap-1"
          role="group"
          aria-label="Concept categories"
        >
          {KIND_PILL_ORDER.map((id) => {
            const meta = ONTOLOGY_KIND_FILTERS.find((item) => item.id === id);
            const active = kindFilters.includes(id);
            return (
              <button
                key={id}
                type="button"
                aria-pressed={active}
                data-hint={meta?.hint}
                className={cn(
                  "galaxy-chip galaxy-hint shrink-0 rounded-full px-2.5 py-1 text-[11px] font-medium tabular-nums transition-colors",
                  active
                    ? "border-primary/45 bg-primary/15 text-foreground"
                    : "text-muted-foreground hover:bg-muted/40 hover:text-foreground",
                )}
                data-active={active}
                onClick={() => toggleKind(id)}
              >
                {KIND_PILL_LABEL[id]} ({kindCounts[id]})
              </button>
            );
          })}
        </div>

        <ToolbarDivider />

        <div className="flex shrink-0 items-center gap-1" role="group" aria-label="Labels">
          {OVERLAYS.map((item) => (
            <button
              key={item.id}
              type="button"
              aria-pressed={overlay === item.id}
              data-hint={item.hint}
              className={cn(
                "galaxy-chip galaxy-hint shrink-0 rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors",
                overlay === item.id
                  ? "border-info/40 bg-info/15 text-foreground"
                  : "text-muted-foreground hover:bg-muted/40 hover:text-foreground",
              )}
              data-active={overlay === item.id}
              onClick={() => setOverlay(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>

        <ToolbarDivider />

        <div className="flex shrink-0 items-center gap-1" role="group" aria-label="Story">
          <button
            type="button"
            aria-pressed={!journeyId}
            data-hint="No guided path."
            className={cn(
              "galaxy-chip galaxy-hint shrink-0 rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors",
              !journeyId
                ? "border-success/40 bg-success/15 text-foreground"
                : "text-muted-foreground hover:bg-muted/40 hover:text-foreground",
            )}
            data-active={!journeyId}
            onClick={() => selectJourney(null)}
          >
            None
          </button>
          {JOURNEYS.map((item) => (
            <button
              key={item.id}
              type="button"
              aria-pressed={journeyId === item.id}
              data-hint={`Follow ${item.seeds.join(" → ")}.`}
              className={cn(
                "galaxy-chip galaxy-hint shrink-0 rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors",
                journeyId === item.id
                  ? "border-success/40 bg-success/15 text-foreground"
                  : "text-muted-foreground hover:bg-muted/40 hover:text-foreground",
              )}
              data-active={journeyId === item.id}
              onClick={() => selectJourney(item.id)}
            >
              {item.label.replace(" journey", "")}
            </button>
          ))}
        </div>

        {mode === "network" ? (
          <>
            <ToolbarDivider />
            <div className="flex shrink-0 gap-1" role="group" aria-label="Influence metric">
              {METRICS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  data-hint={item.hint}
                  aria-pressed={metric === item.id}
                  aria-label={`${item.label}. ${item.hint}`}
                  className={cn(
                    "galaxy-chip galaxy-hint shrink-0 rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors",
                    metric === item.id
                      ? "border-success/40 bg-success/15 text-foreground"
                      : "text-muted-foreground hover:bg-muted/40",
                  )}
                  data-active={metric === item.id}
                  onClick={() => setMetric(item.id)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </>
        ) : null}

        <div className="ml-auto flex shrink-0 items-center gap-1">
          <Button
            type="button"
            size="sm"
            variant={motionEnabled ? "secondary" : "ghost"}
            className="galaxy-hint h-7 shrink-0 px-2.5 text-[11px]"
            data-hint="Animate nodes and flowing relationship lines."
            aria-pressed={motionEnabled}
            aria-label={`Motion ${motionEnabled ? "on" : "off"}`}
            onClick={() => setMotionEnabled((value) => !value)}
          >
            Motion
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="galaxy-hint h-7 shrink-0 gap-1 px-2.5 text-[11px]"
            data-hint="Show or hide colored community boundaries."
            aria-pressed={showClusters}
            onClick={() => setShowClusters((value) => !value)}
          >
            <Share2 className="size-3.5" />
            {showClusters ? "Zones" : "Flat"}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="galaxy-hint h-7 shrink-0 px-2.5 text-[11px]"
            data-hint="Fit the graph to the canvas."
            onClick={() => void fitView({ padding: 0.08, duration: 400 })}
          >
            Fit
          </Button>
        </div>
      </div>

      <div className="relative z-10 min-h-0 flex-1">
        <ReactFlow
          nodes={flowNodes}
          edges={flowEdges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          fitViewOptions={{ padding: 0.08 }}
          minZoom={0.2}
          maxZoom={2.4}
          proOptions={{ hideAttribution: true }}
          onNodeClick={(_, node) => focusNode(node.id)}
          onPaneClick={() => setSelectedId(null)}
          nodesDraggable
          nodesConnectable={false}
          elementsSelectable
          panOnScroll
          zoomOnScroll
          className="bg-transparent!"
        >
          <Background gap={28} size={1} color="color-mix(in oklab, hsl(var(--foreground)) 8%, transparent)" />
          <Controls showInteractive={false} position="bottom-left" />
          <MiniMap
            pannable
            zoomable
            position="bottom-right"
            maskColor="color-mix(in oklab, hsl(var(--surface-sunken)) 72%, transparent)"
            nodeColor={(node) => (node.data as GalaxyFlowNode["data"]).clusterColor}
            className="!overflow-hidden !rounded-xl !border !border-border/60 !bg-surface-raised/80 !shadow-lg !backdrop-blur"
          />
          {showClusters ? (
            <ClusterLayer
              clusters={graph.clusters}
              nodes={positionedForClusters}
              activeCluster={activeCluster}
              onHover={setActiveCluster}
            />
          ) : null}
          <Panel position="top-left" className="m-3">
            <motion.div
              layout
              className="rounded-2xl border border-border/50 bg-surface-raised/75 px-3 py-2 text-[11px] shadow-lg backdrop-blur-xl"
            >
              <div className="flex items-center gap-2 font-semibold tracking-tight">
                <Sparkles className="size-3.5 text-success" />
                {MODES.find((item) => item.id === mode)?.label} · {graph.metadata.nodeCount} concepts ·{" "}
                {graph.metadata.edgeCount} links
              </div>
              {journeyPath.length ? (
                <p className="mt-1 max-w-[16rem] text-muted-foreground">
                  {journeyPath
                    .map((id) => nodeById.get(id)?.label ?? id)
                    .join(" → ")}
                </p>
              ) : selectedId ? (
                <p className="mt-1 text-muted-foreground">
                  Explore · {relationshipCount} neighbors · 2-hop neighborhood
                </p>
              ) : (
                <p className="mt-1 text-muted-foreground">
                  {mode === "semantic"
                    ? "Click a concept to expand its semantic neighborhood"
                    : mode === "network"
                      ? "Influence sized by connectivity — hover a community"
                      : "Taxonomy of business meaning, not physical tables"}
                </p>
              )}
            </motion.div>
          </Panel>
          <Panel position="top-right" className="m-3">
            <div className="flex flex-wrap gap-1.5 rounded-2xl border border-border/50 bg-surface-raised/75 p-2 shadow-lg backdrop-blur-xl">
              {(Object.keys(EDGE_STYLES) as Array<keyof typeof EDGE_STYLES>).map((key) => (
                <span
                  key={key}
                  className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium text-muted-foreground"
                >
                  <span
                    className="size-1.5 rounded-full"
                    style={{ background: EDGE_STYLES[key].color, boxShadow: `0 0 8px ${EDGE_STYLES[key].color}` }}
                  />
                  {EDGE_STYLES[key].label}
                </span>
              ))}
            </div>
          </Panel>
        </ReactFlow>

        <NodeDrawer
          node={selectedNode}
          snapshot={graph}
          overlay={overlay}
          onClose={() => setSelectedId(null)}
          onFocus={focusNode}
        />
      </div>
    </div>
  );
}

function ToolbarDivider() {
  return <span className="h-4 w-px shrink-0 bg-border/70" aria-hidden="true" />;
}
