"use client";

import type { OntologyEdge, OntologySnapshot } from "@nql/shared-types";
import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type EdgeTypes,
  type NodeChange,
  type NodeTypes,
} from "@xyflow/react";
import { BookOpen, GitFork, Network, Share2, Sparkles } from "lucide-react";
import * as React from "react";

import { ClusterLayer, clusterLabelBox, clusterZones } from "@/components/ontology/cluster-layer";
import { GalaxyEdge, EDGE_STYLES, type GalaxyFlowEdge } from "@/components/ontology/galaxy-edge";
import { GalaxyNode, type GalaxyFlowNode } from "@/components/ontology/galaxy-node";
import "@/components/ontology/galaxy-styles.css";
import { NodeDrawer } from "@/components/ontology/node-drawer";
import { ParticleField } from "@/components/ontology/particle-field";
import { Button } from "@/components/ui/button";
import { displayName, storyLabel, type ContextOverlay } from "@/lib/ontology/asset-context";
import { placeEdgeLabels, type LabelPlacement } from "@/lib/ontology/edge-geometry";
import {
  CONCEPT_CATEGORIES,
  nodeMatchesKindFilter,
  nodeMatchesKindFilters,
  type OntologyKindFilter,
} from "@/lib/ontology/kind-filter";
import {
  CAPTION_HEIGHT,
  edgeVisualKind,
  layoutGalaxy,
  type CentralityMetric,
  type GalaxyMode,
  type PositionedNode,
} from "@/lib/ontology/layouts";
import { mergeOntologyConcepts, withoutDomainNodes } from "@/lib/ontology/merge-concepts";
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
    hint: "Every business concept once, grouped by category, linked by named relationships.",
    icon: Sparkles,
  },
  {
    id: "network",
    label: "Relationship Network",
    hint: "The same concepts sized by importance, so the hubs of the business stand out.",
    icon: Share2,
  },
  {
    id: "hierarchy",
    label: "Hierarchy",
    hint: "Top to bottom roll-up: Region → Dealer → Sale → Revenue.",
    icon: GitFork,
  },
];

const METRICS: ReadonlyArray<{ id: CentralityMetric; label: string; hint: string }> = [
  { id: "degree", label: "Most connected", hint: "Bigger circles have more direct relationships." },
  { id: "betweenness", label: "Bridges", hint: "Bigger circles connect otherwise separate parts of the business." },
  { id: "pagerank", label: "Most influential", hint: "Bigger circles are linked to by other important concepts." },
];

const OVERLAYS: ReadonlyArray<{ id: ContextOverlay; label: string; hint: string }> = [
  { id: "business", label: "Business names", hint: "Everyday business language, as used in questions." },
  { id: "technical", label: "Technical names", hint: "Database tables and join columns behind each concept." },
];

const MODE_HINT: Record<GalaxyMode, string> = {
  semantic: "Click a concept to see what it connects to",
  network: "Larger circles are the hubs of the business",
  hierarchy: "Each row rolls up into the row above it",
};

type Geometry = { diameter: number; boxWidth: number };

function geometryOf(node: PositionedNode): Geometry {
  const diameter = Math.round(Math.min(110, Math.max(40, node.radius * 2)));
  return { diameter, boxWidth: Math.max(diameter, node.captionWidth) };
}

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
  const { fitView, setCenter, getZoom } = useReactFlow();
  const [mode, setMode] = React.useState<GalaxyMode>("semantic");
  const [metric, setMetric] = React.useState<CentralityMetric>("degree");
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [showZones, setShowZones] = React.useState(true);
  const [motionEnabled, setMotionEnabled] = React.useState(false);
  const [kindFilters, setKindFilters] = React.useState<OntologyKindFilter[]>(["all"]);
  const [overlay, setOverlay] = React.useState<ContextOverlay>("business");
  const zonesVisible = showZones && mode === "semantic";

  const graph = React.useMemo(() => mergeOntologyConcepts(withoutDomainNodes(snapshot)), [snapshot]);

  const positioned = React.useMemo(() => layoutGalaxy(graph, mode, metric), [graph, mode, metric]);

  // Dragged positions belong to one layout; switching view starts from a clean layout.
  const [drag, setDrag] = React.useState<{
    layout: PositionedNode[];
    moves: Record<string, { x: number; y: number }>;
  }>({ layout: positioned, moves: {} });
  const moves = drag.layout === positioned ? drag.moves : null;

  const live = React.useMemo(
    () =>
      positioned.map((node) => {
        const moved = moves?.[node.id];
        return moved ? { ...node, x: moved.x, y: moved.y } : node;
      }),
    [positioned, moves],
  );

  const geometry = React.useMemo(
    () => new Map(positioned.map((node) => [node.id, geometryOf(node)])),
    [positioned],
  );

  const nodeById = React.useMemo(() => new Map(graph.nodes.map((node) => [node.id, node])), [graph.nodes]);

  const edgeLabel = React.useCallback(
    (edge: OntologyEdge) =>
      storyLabel(edge, overlay) || EDGE_STYLES[edgeVisualKind(edge, nodeById)].label,
    [overlay, nodeById],
  );

  const labelPlacement = React.useMemo(() => {
    const byId = new Map(positioned.map((node) => [node.id, node]));
    const obstacles = positioned.map((node) => {
      const geo = geometry.get(node.id)!;
      return {
        x: node.x - geo.boxWidth / 2,
        y: node.y - geo.diameter / 2,
        width: geo.boxWidth,
        height: geo.diameter + CAPTION_HEIGHT,
      };
    });
    if (zonesVisible) {
      for (const zone of clusterZones(graph.clusters, positioned)) obstacles.push(clusterLabelBox(zone));
    }
    const baseCurve = mode === "hierarchy" ? 0.08 : 0.16;
    const inputs = graph.edges.flatMap((edge) => {
      const source = byId.get(edge.source);
      const target = byId.get(edge.target);
      if (!source || !target) return [];
      return [
        {
          id: edge.id,
          label: edgeLabel(edge),
          source: { x: source.x, y: source.y },
          target: { x: target.x, y: target.y },
          sourceRadius: geometry.get(source.id)!.diameter / 2 + 4,
          targetRadius: geometry.get(target.id)!.diameter / 2 + 4,
          curvature: baseCurve,
        },
      ];
    });
    return placeEdgeLabels(inputs, obstacles);
  }, [positioned, geometry, graph.edges, graph.clusters, edgeLabel, mode, zonesVisible]);

  const neighbors = React.useMemo(() => {
    if (!selectedId) return null;
    const nodes = new Set<string>([selectedId]);
    const edges = new Set<string>();
    for (const edge of graph.edges) {
      if (edge.source === selectedId || edge.target === selectedId) {
        edges.add(edge.id);
        nodes.add(edge.source);
        nodes.add(edge.target);
      }
    }
    return { nodes, edges };
  }, [selectedId, graph.edges]);

  const filtering = !kindFilters.includes("all");

  const flowNodes: GalaxyFlowNode[] = React.useMemo(
    () =>
      live.map((node) => {
        const geo = geometry.get(node.id)!;
        const inFilter = nodeMatchesKindFilters(node, kindFilters);
        const selected = node.id === selectedId;
        const neighbor = Boolean(neighbors?.nodes.has(node.id)) && !selected;
        const dimmed = neighbors ? !neighbors.nodes.has(node.id) : !inFilter;
        return {
          id: node.id,
          type: "galaxy",
          position: { x: node.x - geo.boxWidth / 2, y: node.y - geo.diameter / 2 },
          width: geo.boxWidth,
          height: geo.diameter + CAPTION_HEIGHT + 6,
          data: {
            ...node,
            diameter: geo.diameter,
            boxWidth: geo.boxWidth,
            dimmed,
            selectedConcept: selected,
            neighbor,
            displayLabel: displayName(node, overlay),
          },
          zIndex: selected ? 30 : neighbor ? 20 : dimmed ? 1 : 10,
        };
      }),
    [live, geometry, kindFilters, selectedId, neighbors, overlay],
  );

  const flowEdges: GalaxyFlowEdge[] = React.useMemo(
    () =>
      graph.edges.map((edge) => {
        const visualKind = edgeVisualKind(edge, nodeById);
        const source = nodeById.get(edge.source);
        const target = nodeById.get(edge.target);
        const touchesFilter =
          !filtering ||
          (source ? nodeMatchesKindFilters(source, kindFilters) : false) ||
          (target ? nodeMatchesKindFilters(target, kindFilters) : false);
        const emphasized = neighbors ? neighbors.edges.has(edge.id) : filtering && touchesFilter;
        const dimmed = neighbors ? !neighbors.edges.has(edge.id) : !touchesFilter;
        const placement: LabelPlacement = labelPlacement.get(edge.id) ?? {
          curvature: 0.16,
          labelT: 0.5,
        };
        const color = EDGE_STYLES[visualKind].color;
        return {
          id: edge.id,
          type: "galaxy",
          source: edge.source,
          target: edge.target,
          markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
          data: {
            visualKind,
            label: edgeLabel(edge),
            dimmed,
            emphasized,
            curvature: placement.curvature,
            labelT: placement.labelT,
            motionEnabled,
          },
          zIndex: emphasized ? 4 : 0,
        };
      }),
    [graph.edges, nodeById, filtering, kindFilters, neighbors, labelPlacement, edgeLabel, motionEnabled],
  );

  const onNodesChange = React.useCallback(
    (changes: NodeChange<GalaxyFlowNode>[]) => {
      const updates: Record<string, { x: number; y: number }> = {};
      for (const change of changes) {
        if (change.type !== "position" || !change.position) continue;
        const geo = geometry.get(change.id);
        if (!geo) continue;
        updates[change.id] = {
          x: change.position.x + geo.boxWidth / 2,
          y: change.position.y + geo.diameter / 2,
        };
      }
      if (!Object.keys(updates).length) return;
      setDrag((current) => ({
        layout: positioned,
        moves: { ...(current.layout === positioned ? current.moves : {}), ...updates },
      }));
    },
    [geometry, positioned],
  );

  const kindCounts = React.useMemo(() => {
    const counts: Record<string, number> = { all: graph.nodes.length };
    for (const category of CONCEPT_CATEGORIES) {
      counts[category.id] = graph.nodes.filter((node) => nodeMatchesKindFilter(node, category.id)).length;
    }
    return counts;
  }, [graph.nodes]);

  const visibleCategories = CONCEPT_CATEGORIES.filter((category) => kindCounts[category.id]);

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
      void fitView({ padding: 0.1, duration: 400 });
    }, 60);
    return () => window.clearTimeout(timer);
  }, [positioned, fitView]);

  const liveRef = React.useRef(live);
  React.useEffect(() => {
    liveRef.current = live;
  }, [live]);

  const panTo = React.useCallback(
    (nodeId: string) => {
      setSelectedId(nodeId);
      const node = liveRef.current.find((item) => item.id === nodeId);
      if (!node) return;
      void setCenter(node.x, node.y, { zoom: Math.max(getZoom(), 0.9), duration: 500 });
    },
    [setCenter, getZoom],
  );

  React.useEffect(() => {
    if (!initialFocusId) return;
    const needle = initialFocusId.toLowerCase();
    const match =
      graph.nodes.find((node) => node.id === initialFocusId) ??
      graph.nodes.find(
        (node) =>
          node.id.toLowerCase().includes(needle) ||
          node.label.toLowerCase().includes(needle) ||
          node.synonyms.some((alias) => alias.toLowerCase() === needle),
      );
    if (!match) return;
    const timer = window.setTimeout(() => panTo(match.id), 500);
    return () => window.clearTimeout(timer);
  }, [initialFocusId, graph.nodes, panTo]);

  const selectedNode = selectedId ? (nodeById.get(selectedId) ?? null) : null;

  return (
    <div
      className="semantic-galaxy relative flex h-full min-h-0 w-full flex-col"
      data-motion={motionEnabled ? "on" : "off"}
      data-mode={mode}
    >
      {motionEnabled ? <ParticleField /> : null}

      <div className="galaxy-toolbar relative z-20 flex shrink-0 items-center gap-2 overflow-x-auto px-2 py-1.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <div className="flex shrink-0 items-center gap-1" role="tablist" aria-label="Graph view">
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
                data-active={active}
                className={cn(
                  "galaxy-chip galaxy-hint inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium",
                  active
                    ? "border-primary/40 bg-primary/15 text-foreground"
                    : "border-transparent text-muted-foreground hover:bg-muted/40 hover:text-foreground",
                )}
                onClick={() => setMode(item.id)}
              >
                <Icon className="size-3" />
                {item.label}
              </button>
            );
          })}
        </div>

        <ToolbarDivider />

        <div className="flex shrink-0 items-center gap-1" role="group" aria-label="Concept categories">
          <CategoryPill
            label="All"
            count={kindCounts.all ?? 0}
            active={kindFilters.includes("all")}
            hint="Show every business concept."
            onClick={() => toggleKind("all")}
          />
          {visibleCategories.map((category) => (
            <CategoryPill
              key={category.id}
              label={category.label}
              count={kindCounts[category.id] ?? 0}
              color={category.color}
              active={kindFilters.includes(category.id)}
              hint={category.hint}
              onClick={() => toggleKind(category.id)}
            />
          ))}
        </div>

        <ToolbarDivider />

        <div className="flex shrink-0 items-center gap-1" role="group" aria-label="Names">
          {OVERLAYS.map((item) => (
            <button
              key={item.id}
              type="button"
              aria-pressed={overlay === item.id}
              data-hint={item.hint}
              data-active={overlay === item.id}
              className={cn(
                "galaxy-chip galaxy-hint shrink-0 rounded-full px-2.5 py-1 text-[11px] font-medium",
                overlay === item.id
                  ? "border-info/40 bg-info/15 text-foreground"
                  : "text-muted-foreground hover:bg-muted/40 hover:text-foreground",
              )}
              onClick={() => setOverlay(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>

        {mode === "network" ? (
          <>
            <ToolbarDivider />
            <div className="flex shrink-0 gap-1" role="group" aria-label="Size circles by">
              {METRICS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  data-hint={item.hint}
                  aria-pressed={metric === item.id}
                  data-active={metric === item.id}
                  className={cn(
                    "galaxy-chip galaxy-hint shrink-0 rounded-full px-2.5 py-1 text-[11px] font-medium",
                    metric === item.id
                      ? "border-success/40 bg-success/15 text-foreground"
                      : "text-muted-foreground hover:bg-muted/40",
                  )}
                  onClick={() => setMetric(item.id)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </>
        ) : null}

        <div className="ml-auto flex shrink-0 items-center gap-1">
          {mode === "semantic" ? (
            <Button
              type="button"
              size="sm"
              variant={showZones ? "secondary" : "ghost"}
              className="galaxy-hint h-7 shrink-0 gap-1 px-2.5 text-[11px]"
              data-hint="Shade the area each business category occupies."
              aria-pressed={showZones}
              onClick={() => setShowZones((value) => !value)}
            >
              <Network className="size-3.5" />
              Groups
            </Button>
          ) : null}
          <Button
            type="button"
            size="sm"
            variant={motionEnabled ? "secondary" : "ghost"}
            className="galaxy-hint h-7 shrink-0 px-2.5 text-[11px]"
            data-hint="Animate the selected concept's relationships."
            aria-pressed={motionEnabled}
            onClick={() => setMotionEnabled((value) => !value)}
          >
            Motion
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="galaxy-hint h-7 shrink-0 px-2.5 text-[11px]"
            data-hint="Fit the whole graph on screen."
            onClick={() => void fitView({ padding: 0.1, duration: 400 })}
          >
            Fit
          </Button>
          <a
            href="/knowledge-graph-guide.html"
            target="_blank"
            rel="noreferrer"
            className="galaxy-hint inline-flex h-7 shrink-0 items-center gap-1 rounded-md px-2.5 text-[11px] font-medium text-muted-foreground hover:bg-muted/40 hover:text-foreground"
            data-hint="How to read this graph, in plain business language."
          >
            <BookOpen className="size-3.5" />
            Guide
          </a>
        </div>
      </div>

      <div className="relative z-10 min-h-0 flex-1">
        <ReactFlow
          nodes={flowNodes}
          edges={flowEdges}
          onNodesChange={onNodesChange}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          fitViewOptions={{ padding: 0.1 }}
          minZoom={0.15}
          maxZoom={2.2}
          proOptions={{ hideAttribution: true }}
          onNodeClick={(_, node) => setSelectedId(node.id)}
          onPaneClick={() => setSelectedId(null)}
          nodesDraggable
          nodeDragThreshold={4}
          nodesConnectable={false}
          elementsSelectable={false}
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
          {zonesVisible ? <ClusterLayer clusters={graph.clusters} nodes={live} /> : null}
          <Panel position="top-left" className="m-3">
            <div className="rounded-2xl border border-border/50 bg-surface-raised/80 px-3 py-2 text-[11px] shadow-lg backdrop-blur-xl">
              <div className="flex items-center gap-2 font-semibold tracking-tight">
                <Sparkles className="size-3.5 text-success" />
                {MODES.find((item) => item.id === mode)?.label} · {graph.metadata.nodeCount} concepts ·{" "}
                {graph.metadata.edgeCount} relationships
              </div>
              <p className="mt-1 max-w-[18rem] text-muted-foreground">
                {selectedNode
                  ? `${selectedNode.label} · ${neighbors ? neighbors.edges.size : 0} direct relationships`
                  : MODE_HINT[mode]}
              </p>
            </div>
          </Panel>
          <Panel position="top-right" className="m-3">
            <div className="rounded-2xl border border-border/50 bg-surface-raised/80 px-3 py-2 text-[10px] shadow-lg backdrop-blur-xl">
              <p className="mb-1 font-semibold text-foreground">Read each arrow as a sentence</p>
              <p className="mb-1.5 text-muted-foreground">Sale → sold by → Dealer</p>
              <div className="flex flex-col gap-1">
                {(Object.keys(EDGE_STYLES) as Array<keyof typeof EDGE_STYLES>).map((key) => (
                  <span key={key} className="inline-flex items-center gap-1.5 text-muted-foreground">
                    <span className="h-0.5 w-4 rounded-full" style={{ background: EDGE_STYLES[key].color }} />
                    {EDGE_STYLES[key].label}
                  </span>
                ))}
              </div>
            </div>
          </Panel>
        </ReactFlow>

        <NodeDrawer
          node={selectedNode}
          snapshot={graph}
          overlay={overlay}
          onClose={() => setSelectedId(null)}
          onFocus={panTo}
        />
      </div>
    </div>
  );
}

function CategoryPill({
  label,
  count,
  color,
  active,
  hint,
  onClick,
}: {
  label: string;
  count: number;
  color?: string;
  active: boolean;
  hint: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      data-hint={hint}
      data-active={active}
      className={cn(
        "galaxy-chip galaxy-hint inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium tabular-nums",
        active
          ? "border-primary/45 bg-primary/15 text-foreground"
          : "text-muted-foreground hover:bg-muted/40 hover:text-foreground",
      )}
      onClick={onClick}
    >
      {color ? <span className="size-2 rounded-full" style={{ background: color }} aria-hidden="true" /> : null}
      {label} ({count})
    </button>
  );
}

function ToolbarDivider() {
  return <span className="h-4 w-px shrink-0 bg-border/70" aria-hidden="true" />;
}
