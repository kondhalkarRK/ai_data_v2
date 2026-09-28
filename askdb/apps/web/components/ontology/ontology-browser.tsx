"use client";

import type {
  OntologyEdge,
  OntologyNode,
  OntologySnapshot,
} from "@nql/shared-types";
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
import { BookOpen, Network, Orbit, Radar, Share2, Tags } from "lucide-react";
import * as React from "react";

import {
  ClusterLayer,
  RingLayer,
  clusterLabelBox,
  clusterZones,
} from "@/components/ontology/cluster-layer";
import {
  GalaxyEdge,
  EDGE_STYLES,
  type GalaxyFlowEdge,
} from "@/components/ontology/galaxy-edge";
import {
  GalaxyNode,
  type GalaxyFlowNode,
  type NodeVariant,
} from "@/components/ontology/galaxy-node";
import "@/components/ontology/galaxy-styles.css";
import { NodeDrawer } from "@/components/ontology/node-drawer";
import { ParticleField } from "@/components/ontology/particle-field";
import { Button } from "@/components/ui/button";
import {
  displayName,
  storyLabel,
  type ContextOverlay,
} from "@/lib/ontology/asset-context";
import {
  placeEdgeLabels,
  type LabelPlacement,
} from "@/lib/ontology/edge-geometry";
import {
  CONCEPT_CATEGORIES,
  categoryMeta,
  conceptCategory,
  nodeMatchesKindFilter,
  nodeMatchesKindFilters,
  type OntologyKindFilter,
} from "@/lib/ontology/kind-filter";
import {
  CONNECTED_FILTER_HINT,
  KNOWLEDGE_CATEGORIES,
  KNOWLEDGE_EDGE_STYLES,
  buildKnowledgeGraph,
  knowledgeCategory,
  knowledgeEdgeKind,
  knowledgeMeta,
  knowledgeVisibleIds,
  type KnowledgeFilter,
} from "@/lib/ontology/knowledge-graph";
import {
  CAPTION_HEIGHT,
  edgeVisualKind,
  influenceRingRadii,
  layoutGalaxy,
  type CentralityMetric,
  type GalaxyMode,
  type GraphLayout,
  type PositionedNode,
} from "@/lib/ontology/layouts";
import {
  mergeOntologyConcepts,
  withoutDomainNodes,
} from "@/lib/ontology/merge-concepts";
import { cn } from "@/lib/utils";

const nodeTypes: NodeTypes = { galaxy: GalaxyNode };
const edgeTypes: EdgeTypes = { galaxy: GalaxyEdge };

const MODES: ReadonlyArray<{
  id: GalaxyMode;
  label: string;
  badge?: string;
  hint: string;
  icon: React.ComponentType<{ className?: string }>;
}> = [
  {
    id: "knowledge",
    label: "Knowledge Graph",
    badge: "Recommended",
    hint: "Explore how actors, events, entities, attributes and outcomes relate. Click a concept to expand two steps out.",
    icon: Orbit,
  },
  {
    id: "network",
    label: "Relationship Network",
    hint: "Find the hubs. The most central concept sits in the middle; each ring outwards is less central.",
    icon: Radar,
  },
  {
    id: "simple",
    label: "Simple Relationship View",
    hint: "Every business concept once, every relationship labelled. The quickest way to read the model.",
    icon: Share2,
  },
];

const SIMPLE_LAYOUTS: ReadonlyArray<{
  id: GraphLayout;
  label: string;
  hint: string;
}> = [
  {
    id: "grouped",
    label: "Grouped",
    hint: "Concepts grouped by business category.",
  },
  {
    id: "rollup",
    label: "Top-down",
    hint: "Each row rolls up into the row above: Region → Dealer → Sale → Revenue.",
  },
];

const METRICS: ReadonlyArray<{
  id: CentralityMetric;
  label: string;
  hint: string;
}> = [
  {
    id: "degree",
    label: "Most connected",
    hint: "Ranked by number of direct relationships.",
  },
  {
    id: "betweenness",
    label: "Bridges",
    hint: "Ranked by how often a concept links otherwise separate parts.",
  },
  {
    id: "pagerank",
    label: "Most influential",
    hint: "Ranked by links from other important concepts.",
  },
];

const OVERLAYS: ReadonlyArray<{
  id: ContextOverlay;
  label: string;
  hint: string;
}> = [
  {
    id: "business",
    label: "Business names",
    hint: "Everyday business language, as used in questions.",
  },
  {
    id: "technical",
    label: "Technical names",
    hint: "Database tables and join columns behind each concept.",
  },
];

const MODE_HINT: Record<GalaxyMode, string> = {
  knowledge: "Click a concept to expand its neighbourhood two steps out",
  network: "Centre = most central concept · outer rings = less central",
  simple: "Each business concept once, grouped by category · every relationship labelled",
};

const VARIANT: Record<GalaxyMode, NodeVariant> = {
  knowledge: "orb",
  network: "hub",
  simple: "concept",
};

type Geometry = { diameter: number; boxWidth: number };

function geometryOf(node: PositionedNode, mode: GalaxyMode): Geometry {
  const min = mode === "network" ? 34 : 40;
  const diameter = Math.round(Math.min(110, Math.max(min, node.radius * 2)));
  return { diameter, boxWidth: Math.max(diameter, node.captionWidth) };
}

type Focus = {
  hop1: Set<string>;
  hop2: Set<string>;
  edges1: Set<string>;
  edges2: Set<string>;
};

function focusOf(
  selectedId: string,
  edges: OntologyEdge[],
  twoHops: boolean,
): Focus {
  const hop1 = new Set<string>();
  const edges1 = new Set<string>();
  for (const edge of edges) {
    if (edge.source === selectedId || edge.target === selectedId) {
      edges1.add(edge.id);
      hop1.add(edge.source === selectedId ? edge.target : edge.source);
    }
  }
  const hop2 = new Set<string>();
  const edges2 = new Set<string>();
  if (twoHops) {
    for (const edge of edges) {
      if (edges1.has(edge.id)) continue;
      const fromHop1 = hop1.has(edge.source)
        ? edge.target
        : hop1.has(edge.target)
          ? edge.source
          : null;
      if (fromHop1 === null || fromHop1 === selectedId) continue;
      edges2.add(edge.id);
      if (!hop1.has(fromHop1)) hop2.add(fromHop1);
    }
  }
  return { hop1, hop2, edges1, edges2 };
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
      <OntologyBrowserInner
        snapshot={snapshot}
        initialFocusId={initialFocusId}
      />
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
  const [mode, setMode] = React.useState<GalaxyMode>("knowledge");
  const [simpleLayout, setSimpleLayout] =
    React.useState<GraphLayout>("grouped");
  const [metric, setMetric] = React.useState<CentralityMetric>("degree");
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [showZones, setShowZones] = React.useState(true);
  const [showLabels, setShowLabels] = React.useState(false);
  const [motionEnabled, setMotionEnabled] = React.useState(false);
  const [knowledgeFilters, setKnowledgeFilters] = React.useState<
    KnowledgeFilter[]
  >(["all"]);
  const [simpleFilters, setSimpleFilters] = React.useState<
    OntologyKindFilter[]
  >(["all"]);
  const [overlay, setOverlay] = React.useState<ContextOverlay>("business");

  const isSimple = mode === "simple";
  const layout: GraphLayout =
    mode === "knowledge"
      ? "knowledge"
      : mode === "network"
        ? "influence"
        : simpleLayout;
  const zonesVisible =
    showZones && (layout === "knowledge" || layout === "grouped");
  const labelsVisible = isSimple || showLabels;

  const knowledgeGraph = React.useMemo(
    () => buildKnowledgeGraph(snapshot),
    [snapshot],
  );
  const simpleGraph = React.useMemo(
    () => mergeOntologyConcepts(withoutDomainNodes(snapshot)),
    [snapshot],
  );
  const graph = isSimple ? simpleGraph : knowledgeGraph;

  const categoryOf = React.useCallback(
    (node: OntologyNode) =>
      isSimple ? conceptCategory(node) : knowledgeCategory(node),
    [isSimple],
  );
  const categoryLabelOf = React.useCallback(
    (node: OntologyNode) =>
      isSimple
        ? categoryMeta(conceptCategory(node)).label
        : knowledgeMeta(knowledgeCategory(node)).label,
    [isSimple],
  );

  const positioned = React.useMemo(
    () => layoutGalaxy(graph, layout, metric),
    [graph, layout, metric],
  );

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
    () => new Map(positioned.map((node) => [node.id, geometryOf(node, mode)])),
    [positioned, mode],
  );

  const rankById = React.useMemo(() => {
    const ranked = [...positioned].sort((a, b) => b.centrality - a.centrality);
    return new Map(ranked.map((node, index) => [node.id, index + 1]));
  }, [positioned]);

  const nodeById = React.useMemo(
    () => new Map(graph.nodes.map((node) => [node.id, node])),
    [graph.nodes],
  );

  const edgeColor = React.useCallback(
    (edge: OntologyEdge) =>
      isSimple
        ? EDGE_STYLES[edgeVisualKind(edge, nodeById)].color
        : KNOWLEDGE_EDGE_STYLES[knowledgeEdgeKind(edge, nodeById)].color,
    [isSimple, nodeById],
  );

  const edgeLabel = React.useCallback(
    (edge: OntologyEdge) =>
      storyLabel(edge, overlay) ||
      (isSimple
        ? EDGE_STYLES[edgeVisualKind(edge, nodeById)].label
        : KNOWLEDGE_EDGE_STYLES[knowledgeEdgeKind(edge, nodeById)].label),
    [overlay, isSimple, nodeById],
  );

  const baseCurve =
    layout === "influence"
      ? 0
      : layout === "rollup"
        ? 0.08
        : layout === "knowledge"
          ? 0.22
          : 0.16;

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
      for (const zone of clusterZones(graph.clusters, positioned))
        obstacles.push(clusterLabelBox(zone));
    }
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
  }, [
    positioned,
    geometry,
    graph.edges,
    graph.clusters,
    edgeLabel,
    zonesVisible,
    baseCurve,
  ]);

  const focus = React.useMemo(
    () =>
      selectedId
        ? focusOf(selectedId, graph.edges, mode === "knowledge")
        : null,
    [selectedId, graph.edges, mode],
  );

  const visibleIds = React.useMemo(() => {
    if (isSimple) {
      if (simpleFilters.includes("all")) return null;
      return new Set(
        graph.nodes
          .filter((node) => nodeMatchesKindFilters(node, simpleFilters))
          .map((node) => node.id),
      );
    }
    return knowledgeVisibleIds(graph, knowledgeFilters);
  }, [isSimple, simpleFilters, knowledgeFilters, graph]);

  const flowNodes: GalaxyFlowNode[] = React.useMemo(
    () =>
      live.map((node) => {
        const geo = geometry.get(node.id)!;
        const selected = node.id === selectedId;
        const hop = focus?.hop1.has(node.id)
          ? 1
          : focus?.hop2.has(node.id)
            ? 2
            : null;
        const dimmed = focus
          ? !selected && hop === null
          : visibleIds
            ? !visibleIds.has(node.id)
            : false;
        return {
          id: node.id,
          type: "galaxy",
          position: {
            x: node.x - geo.boxWidth / 2,
            y: node.y - geo.diameter / 2,
          },
          width: geo.boxWidth,
          height: geo.diameter + CAPTION_HEIGHT + 6,
          data: {
            ...node,
            variant: VARIANT[mode],
            category: categoryOf(node),
            color: node.clusterColor,
            diameter: geo.diameter,
            boxWidth: geo.boxWidth,
            dimmed,
            selectedConcept: selected,
            hop,
            rank: rankById.get(node.id),
            displayLabel: displayName(node, overlay),
          },
          zIndex: selected
            ? 30
            : hop === 1
              ? 20
              : hop === 2
                ? 15
                : dimmed
                  ? 1
                  : 10,
        };
      }),
    [
      live,
      geometry,
      selectedId,
      focus,
      visibleIds,
      mode,
      categoryOf,
      rankById,
      overlay,
    ],
  );

  const flowEdges: GalaxyFlowEdge[] = React.useMemo(
    () =>
      graph.edges.map((edge) => {
        const touchesFilter =
          !visibleIds ||
          (isSimple
            ? visibleIds.has(edge.source) || visibleIds.has(edge.target)
            : visibleIds.has(edge.source) && visibleIds.has(edge.target));
        const emphasized = focus
          ? focus.edges1.has(edge.id)
          : Boolean(visibleIds) && touchesFilter;
        const secondary = Boolean(focus?.edges2.has(edge.id));
        const dimmed = focus ? !emphasized && !secondary : !touchesFilter;
        const placement: LabelPlacement = labelPlacement.get(edge.id) ?? {
          curvature: baseCurve,
          labelT: 0.5,
        };
        const color = edgeColor(edge);
        const arrow = mode === "network" ? 12 : 16;
        return {
          id: edge.id,
          type: "galaxy",
          source: edge.source,
          target: edge.target,
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color,
            width: arrow,
            height: arrow,
          },
          data: {
            color,
            label: edgeLabel(edge),
            labelVisible: labelsVisible,
            dimmed,
            emphasized,
            secondary,
            curvature: placement.curvature,
            labelT: placement.labelT,
            glow: mode === "knowledge",
            motionEnabled,
          },
          zIndex: emphasized ? 4 : secondary ? 2 : 0,
        };
      }),
    [
      graph.edges,
      visibleIds,
      isSimple,
      focus,
      labelPlacement,
      baseCurve,
      edgeColor,
      edgeLabel,
      labelsVisible,
      mode,
      motionEnabled,
    ],
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
        moves: {
          ...(current.layout === positioned ? current.moves : {}),
          ...updates,
        },
      }));
    },
    [geometry, positioned],
  );

  const simpleCounts = React.useMemo(() => {
    const counts: Record<string, number> = { all: simpleGraph.nodes.length };
    for (const category of CONCEPT_CATEGORIES) {
      counts[category.id] = simpleGraph.nodes.filter((node) =>
        nodeMatchesKindFilter(node, category.id),
      ).length;
    }
    return counts;
  }, [simpleGraph.nodes]);

  const knowledgeCounts = React.useMemo(() => {
    const counts: Record<string, number> = { all: knowledgeGraph.nodes.length };
    for (const category of KNOWLEDGE_CATEGORIES) {
      counts[category.id] = knowledgeGraph.nodes.filter(
        (node) => knowledgeCategory(node) === category.id,
      ).length;
    }
    counts.connected = knowledgeGraph.nodes.filter(
      (node) => node.degree > 0,
    ).length;
    return counts;
  }, [knowledgeGraph.nodes]);

  function toggleFilter<T extends string>(current: T[], id: T): T[] {
    if (id === "all") return ["all" as T];
    const withoutAll = current.filter((item) => item !== "all");
    const next = withoutAll.includes(id)
      ? withoutAll.filter((item) => item !== id)
      : [...withoutAll, id];
    return next.length ? next : ["all" as T];
  }

  function switchMode(next: GalaxyMode) {
    setSelectedId(null);
    setMode(next);
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
      void setCenter(node.x, node.y, {
        zoom: Math.max(getZoom(), 0.9),
        duration: 500,
      });
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
  const ringRadii = React.useMemo(
    () => (layout === "influence" ? influenceRingRadii(positioned) : []),
    [layout, positioned],
  );
  const activeMode = MODES.find((item) => item.id === mode)!;

  return (
    <div
      className="semantic-galaxy relative flex h-full min-h-0 w-full flex-col"
      data-mode={mode}
    >
      <div className="galaxy-toolbar relative z-20 flex shrink-0 flex-col">
        <div className="flex items-center gap-2 overflow-x-auto px-2 py-1.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <div
            className="flex shrink-0 items-center gap-1"
            role="tablist"
            aria-label="Graph view"
          >
            {MODES.map((item) => {
              const Icon = item.icon;
              const active = mode === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  aria-label={`${item.label}${item.badge ? ` (${item.badge})` : ""}. ${item.hint}`}
                  data-hint={item.hint}
                  data-active={active}
                  data-view={item.id}
                  className={cn(
                    "galaxy-chip galaxy-view-tab galaxy-hint inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium",
                    active
                      ? "text-foreground"
                      : "border-transparent text-muted-foreground hover:bg-muted/40 hover:text-foreground",
                  )}
                  onClick={() => switchMode(item.id)}
                >
                  <Icon className="size-3.5" />
                  {item.label}
                  {item.badge ? (
                    <span className="galaxy-view-tab__badge">{item.badge}</span>
                  ) : null}
                </button>
              );
            })}
          </div>
          <div className="ml-auto flex shrink-0 items-center gap-1">
            {!isSimple ? (
              <ToggleButton
                active={showLabels}
                hint="Show every relationship verb. Otherwise verbs appear around the selected concept."
                onClick={() => setShowLabels((value) => !value)}
              >
                <Tags className="size-3.5" />
                Labels
              </ToggleButton>
            ) : null}
            {layout === "knowledge" || layout === "grouped" ? (
              <ToggleButton
                active={showZones}
                hint="Shade the area each group occupies."
                onClick={() => setShowZones((value) => !value)}
              >
                Groups
              </ToggleButton>
            ) : null}
            {mode === "knowledge" ? (
              <ToggleButton
                active={motionEnabled}
                hint="Drifting particles and flowing relationships around the selected concept."
                onClick={() => setMotionEnabled((value) => !value)}
              >
                Motion
              </ToggleButton>
            ) : null}
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
              data-hint="What each view is for, in plain business language."
            >
              <BookOpen className="size-3.5" />
              Guide
            </a>
          </div>
        </div>

        <div className="flex items-center gap-2 overflow-x-auto border-t border-border/40 px-2 py-1.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {isSimple ? (
            <div
              className="flex shrink-0 items-center gap-1"
              role="group"
              aria-label="Business categories"
            >
              <CategoryPill
                label="All"
                count={simpleCounts.all ?? 0}
                active={simpleFilters.includes("all")}
                hint="Show every business concept."
                onClick={() =>
                  setSimpleFilters((current) => toggleFilter(current, "all"))
                }
              />
              {CONCEPT_CATEGORIES.filter(
                (category) => simpleCounts[category.id],
              ).map((category) => (
                <CategoryPill
                  key={category.id}
                  label={category.label}
                  count={simpleCounts[category.id] ?? 0}
                  color={category.color}
                  active={simpleFilters.includes(category.id)}
                  hint={category.hint}
                  onClick={() =>
                    setSimpleFilters((current) =>
                      toggleFilter<OntologyKindFilter>(current, category.id),
                    )
                  }
                />
              ))}
            </div>
          ) : (
            <div
              className="flex shrink-0 items-center gap-1"
              role="group"
              aria-label="Knowledge roles"
            >
              <CategoryPill
                label="All"
                count={knowledgeCounts.all ?? 0}
                active={knowledgeFilters.includes("all")}
                hint="Show the whole knowledge graph."
                onClick={() =>
                  setKnowledgeFilters((current) => toggleFilter(current, "all"))
                }
              />
              {KNOWLEDGE_CATEGORIES.filter(
                (category) => knowledgeCounts[category.id],
              ).map((category) => (
                <CategoryPill
                  key={category.id}
                  label={category.label}
                  count={knowledgeCounts[category.id] ?? 0}
                  color={category.color}
                  active={knowledgeFilters.includes(category.id)}
                  hint={category.hint}
                  onClick={() =>
                    setKnowledgeFilters((current) =>
                      toggleFilter<KnowledgeFilter>(current, category.id),
                    )
                  }
                />
              ))}
              <CategoryPill
                label="Connected"
                icon={<Network className="size-3" />}
                active={knowledgeFilters.includes("connected")}
                hint={CONNECTED_FILTER_HINT}
                onClick={() =>
                  setKnowledgeFilters((current) =>
                    toggleFilter<KnowledgeFilter>(current, "connected"),
                  )
                }
              />
            </div>
          )}

          {isSimple ? (
            <>
              <ToolbarDivider />
              <SegmentGroup
                label="Layout"
                items={SIMPLE_LAYOUTS}
                value={simpleLayout}
                onChange={(value) => {
                  setSelectedId(null);
                  setSimpleLayout(value);
                }}
              />
            </>
          ) : null}

          {mode === "network" ? (
            <>
              <ToolbarDivider />
              <SegmentGroup
                label="Rank by"
                items={METRICS}
                value={metric}
                onChange={setMetric}
              />
            </>
          ) : null}

          <ToolbarDivider />
          <SegmentGroup
            label="Names"
            items={OVERLAYS}
            value={overlay}
            onChange={setOverlay}
          />
        </div>
      </div>

      <div
        className="galaxy-canvas relative z-10 min-h-0 flex-1"
        data-mode={mode}
        data-layout={layout}
      >
        {motionEnabled && mode === "knowledge" ? <ParticleField /> : null}
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
          {mode !== "network" ? (
            <Background
              gap={mode === "knowledge" ? 22 : 28}
              size={mode === "knowledge" ? 1.2 : 1}
              color={
                mode === "knowledge"
                  ? "rgba(148, 163, 184, 0.16)"
                  : "color-mix(in oklab, hsl(var(--foreground)) 8%, transparent)"
              }
            />
          ) : null}
          <Controls showInteractive={false} position="bottom-left" />
          <MiniMap
            pannable
            zoomable
            position="bottom-right"
            maskColor={
              mode === "knowledge"
                ? "rgba(3, 7, 18, 0.65)"
                : "color-mix(in oklab, hsl(var(--surface-sunken)) 72%, transparent)"
            }
            nodeColor={(node) => (node.data as GalaxyFlowNode["data"]).color}
            className="galaxy-minimap !overflow-hidden !rounded-xl !border !shadow-lg !backdrop-blur"
          />
          {ringRadii.length ? <RingLayer radii={ringRadii} /> : null}
          {zonesVisible ? (
            <ClusterLayer clusters={graph.clusters} nodes={live} />
          ) : null}
          <Panel position="top-left" className="m-3">
            <div className="galaxy-panel rounded-2xl border px-3 py-2 text-[11px] shadow-lg backdrop-blur-xl">
              <div className="flex items-center gap-2 font-semibold tracking-tight">
                <activeMode.icon className="size-3.5" />
                {activeMode.label} · {graph.metadata.nodeCount} concepts ·{" "}
                {graph.metadata.edgeCount} relationships
              </div>
              <p className="galaxy-panel__muted mt-1 max-w-[20rem]">
                {selectedNode
                  ? mode === "knowledge"
                    ? `${selectedNode.label} · ${focus?.hop1.size ?? 0} direct, ${focus?.hop2.size ?? 0} two steps away`
                    : `${selectedNode.label} · ${focus?.hop1.size ?? 0} direct relationships`
                  : MODE_HINT[mode]}
              </p>
            </div>
          </Panel>
          <Panel position="top-right" className="m-3">
            <Legend mode={mode} metric={metric} />
          </Panel>
        </ReactFlow>

        <NodeDrawer
          node={selectedNode}
          snapshot={graph}
          overlay={overlay}
          categoryLabel={
            selectedNode ? categoryLabelOf(selectedNode) : undefined
          }
          onClose={() => setSelectedId(null)}
          onFocus={panTo}
        />
      </div>
    </div>
  );
}

function Legend({
  mode,
  metric,
}: {
  mode: GalaxyMode;
  metric: CentralityMetric;
}) {
  if (mode === "simple") {
    return (
      <div className="galaxy-panel rounded-2xl border px-3 py-2 text-[10px] shadow-lg backdrop-blur-xl">
        <p className="mb-1 font-semibold">Read each arrow as a sentence</p>
        <p className="galaxy-panel__muted mb-1.5">Sale → sold by → Dealer</p>
        <LegendLines styles={EDGE_STYLES} />
      </div>
    );
  }
  return (
    <div className="galaxy-panel rounded-2xl border px-3 py-2 text-[10px] shadow-lg backdrop-blur-xl">
      {mode === "network" ? (
        <>
          <p className="mb-1 font-semibold">
            Ranked by{" "}
            {METRICS.find((item) => item.id === metric)?.label.toLowerCase()}
          </p>
          <p className="galaxy-panel__muted mb-1.5">
            Bigger and closer to the centre = more central
          </p>
        </>
      ) : (
        <p className="mb-1 font-semibold">Roles</p>
      )}
      <div className="mb-1.5 grid grid-cols-2 gap-x-3 gap-y-1">
        {KNOWLEDGE_CATEGORIES.map((category) => (
          <span
            key={category.id}
            className="galaxy-panel__muted inline-flex items-center gap-1.5"
          >
            <span
              className="size-2 rounded-full"
              style={{ background: category.color }}
            />
            {category.label}
          </span>
        ))}
      </div>
      {mode === "knowledge" ? (
        <LegendLines styles={KNOWLEDGE_EDGE_STYLES} />
      ) : null}
    </div>
  );
}

function LegendLines({
  styles,
}: {
  styles: Record<string, { color: string; label: string }>;
}) {
  return (
    <div className="flex flex-col gap-1">
      {Object.entries(styles).map(([key, style]) => (
        <span
          key={key}
          className="galaxy-panel__muted inline-flex items-center gap-1.5"
        >
          <span
            className="h-0.5 w-4 rounded-full"
            style={{ background: style.color }}
          />
          {style.label}
        </span>
      ))}
    </div>
  );
}

function SegmentGroup<T extends string>({
  label,
  items,
  value,
  onChange,
}: {
  label: string;
  items: ReadonlyArray<{ id: T; label: string; hint: string }>;
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div
      className="flex shrink-0 items-center gap-1"
      role="group"
      aria-label={label}
    >
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          aria-pressed={value === item.id}
          data-hint={item.hint}
          data-active={value === item.id}
          className={cn(
            "galaxy-chip galaxy-hint shrink-0 rounded-full px-2.5 py-1 text-[11px] font-medium",
            value === item.id
              ? "border-info/40 bg-info/15 text-foreground"
              : "text-muted-foreground hover:bg-muted/40 hover:text-foreground",
          )}
          onClick={() => onChange(item.id)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

function ToggleButton({
  active,
  hint,
  onClick,
  children,
}: {
  active: boolean;
  hint: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <Button
      type="button"
      size="sm"
      variant={active ? "secondary" : "ghost"}
      className="galaxy-hint h-7 shrink-0 gap-1 px-2.5 text-[11px]"
      data-hint={hint}
      aria-pressed={active}
      onClick={onClick}
    >
      {children}
    </Button>
  );
}

function CategoryPill({
  label,
  count,
  color,
  icon,
  active,
  hint,
  onClick,
}: {
  label: string;
  count?: number;
  color?: string;
  icon?: React.ReactNode;
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
      {color ? (
        <span
          className="size-2 rounded-full"
          style={{ background: color }}
          aria-hidden="true"
        />
      ) : null}
      {icon}
      {label}
      {count !== undefined ? ` (${count})` : null}
    </button>
  );
}

function ToolbarDivider() {
  return <span className="h-4 w-px shrink-0 bg-border/70" aria-hidden="true" />;
}
