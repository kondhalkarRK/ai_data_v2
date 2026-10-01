"use client";

import type {
  GlossaryTerm,
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
import {
  BookOpen,
  Network,
  Radar,
  Search,
  Shapes,
  Tags,
} from "lucide-react";
import * as React from "react";

import {
  ClusterLayer,
  DomainLayer,
  RingLayer,
  clusterLabelBox,
  clusterZones,
  organicZones,
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
  isFactNode,
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
import {
  buildOntologyMap,
  coreConcepts,
  layoutOntologyMap,
  searchOntology,
  type OntologyMapStyle,
} from "@/lib/ontology/ontology-map";
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
    id: "ontology",
    label: "Ontology Map",
    hint: "Business domains as communities: what areas exist, which concepts matter most, and how the areas connect.",
    icon: Shapes,
  },
  {
    id: "network",
    label: "Relationship Network",
    hint: "Find the hubs. The most central concept sits in the middle; each ring outwards is less central.",
    icon: Radar,
  },
];

const MAP_STYLES: ReadonlyArray<{
  id: OntologyMapStyle;
  label: string;
  hint: string;
}> = [
  {
    id: "force",
    label: "Force",
    hint: "Each business domain settles into its own community.",
  },
  {
    id: "centrality",
    label: "Centrality",
    hint: "Core concepts grow and move to the middle, where domains meet.",
  },
  {
    id: "hierarchy",
    label: "Hierarchy",
    hint: "Each domain as a tree: its most central concept on top.",
  },
];

const CROSS_DOMAIN_COLOR = "#8b5cf6";

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
  ontology: "Pick a domain or search a concept · violet links connect two domains",
};

const VARIANT: Record<GalaxyMode, NodeVariant> = {
  knowledge: "orb",
  network: "hub",
  simple: "concept",
  ontology: "ontology",
};

type Geometry = { diameter: number; boxWidth: number };

function geometryOf(node: PositionedNode, mode: GalaxyMode): Geometry {
  const min = mode === "ontology" ? 26 : mode === "network" ? 34 : 40;
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

function ontologyIcon(node: OntologyNode): string {
  if (isFactNode(node)) return "events";
  if (node.kind === "measure") return "kpis";
  if (node.kind === "dimension") return "attribute";
  return "entities";
}

export function OntologyBrowser({
  snapshot,
  initialFocusId,
  glossary,
}: {
  snapshot: OntologySnapshot;
  initialFocusId?: string | null;
  /** Business glossary terms; the Ontology Map adds them as concepts. */
  glossary?: Record<string, GlossaryTerm>;
}) {
  return (
    <ReactFlowProvider>
      <OntologyBrowserInner
        snapshot={snapshot}
        initialFocusId={initialFocusId}
        glossary={glossary}
      />
    </ReactFlowProvider>
  );
}

function OntologyBrowserInner({
  snapshot,
  initialFocusId,
  glossary,
}: {
  snapshot: OntologySnapshot;
  initialFocusId?: string | null;
  glossary?: Record<string, GlossaryTerm>;
}) {
  const { fitView, setCenter, getZoom } = useReactFlow();
  const [mode, setMode] = React.useState<GalaxyMode>("ontology");
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
  const [mapStyle, setMapStyle] = React.useState<OntologyMapStyle>("force");
  const [domainFocus, setDomainFocus] = React.useState<string | null>(null);
  const [search, setSearch] = React.useState("");

  const isSimple = mode === "simple";
  const isOntology = mode === "ontology";
  const layout: GraphLayout =
    mode === "knowledge"
      ? "knowledge"
      : mode === "network"
        ? "influence"
        : isOntology
          ? "ontology"
          : simpleLayout;
  const zonesVisible =
    showZones && (layout === "knowledge" || layout === "grouped");
  const domainsVisible = showZones && isOntology;
  const labelsVisible = isSimple || showLabels;

  const knowledgeGraph = React.useMemo(
    () => buildKnowledgeGraph(snapshot),
    [snapshot],
  );
  const simpleGraph = React.useMemo(
    () => mergeOntologyConcepts(withoutDomainNodes(snapshot)),
    [snapshot],
  );
  const ontologyMap = React.useMemo(
    () => buildOntologyMap(snapshot, glossary),
    [snapshot, glossary],
  );
  const graph = isOntology
    ? ontologyMap.graph
    : isSimple
      ? simpleGraph
      : knowledgeGraph;

  const domainLabel = React.useMemo(
    () => new Map(ontologyMap.domains.map((domain) => [domain.id, domain.label])),
    [ontologyMap.domains],
  );
  const cores = React.useMemo(
    () => coreConcepts(ontologyMap.graph, 5),
    [ontologyMap.graph],
  );

  const categoryOf = React.useCallback(
    (node: OntologyNode) =>
      isOntology
        ? ontologyIcon(node)
        : isSimple
          ? conceptCategory(node)
          : knowledgeCategory(node),
    [isSimple, isOntology],
  );
  const categoryLabelOf = React.useCallback(
    (node: OntologyNode) =>
      isOntology
        ? `${domainLabel.get(node.cluster) ?? "Other"} domain`
        : isSimple
          ? categoryMeta(conceptCategory(node)).label
          : knowledgeMeta(knowledgeCategory(node)).label,
    [isSimple, isOntology, domainLabel],
  );

  const positioned = React.useMemo(
    () =>
      isOntology
        ? layoutOntologyMap(ontologyMap, mapStyle)
        : layoutGalaxy(graph, layout, metric),
    [isOntology, ontologyMap, mapStyle, graph, layout, metric],
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
    (edge: OntologyEdge) => {
      if (isOntology) {
        return ontologyMap.crossEdges.has(edge.id)
          ? CROSS_DOMAIN_COLOR
          : (nodeById.get(edge.source)?.clusterColor ?? "#94a3b8");
      }
      return isSimple
        ? EDGE_STYLES[edgeVisualKind(edge, nodeById)].color
        : KNOWLEDGE_EDGE_STYLES[knowledgeEdgeKind(edge, nodeById)].color;
    },
    [isOntology, isSimple, nodeById, ontologyMap.crossEdges],
  );

  const edgeLabel = React.useCallback(
    (edge: OntologyEdge) =>
      storyLabel(edge, overlay) ||
      (isSimple || isOntology
        ? EDGE_STYLES[edgeVisualKind(edge, nodeById)].label
        : KNOWLEDGE_EDGE_STYLES[knowledgeEdgeKind(edge, nodeById)].label),
    [overlay, isSimple, isOntology, nodeById],
  );

  const baseCurve =
    layout === "influence"
      ? 0
      : layout === "rollup"
        ? 0.08
        : layout === "knowledge"
          ? 0.22
          : layout === "ontology"
            ? mapStyle === "hierarchy"
              ? 0.1
              : 0.2
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
    if (domainsVisible) {
      for (const zone of organicZones(graph.clusters, positioned))
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
    domainsVisible,
    baseCurve,
  ]);

  const focus = React.useMemo(
    () =>
      selectedId
        ? focusOf(selectedId, graph.edges, mode === "knowledge")
        : null,
    [selectedId, graph.edges, mode],
  );

  const searchResult = React.useMemo(
    () => (isOntology ? searchOntology(graph, search, cores) : null),
    [isOntology, graph, search, cores],
  );

  /** Ontology Map emphasis: a search wins over a focused domain. */
  const highlight = React.useMemo(() => {
    if (!isOntology) return null;
    if (searchResult) {
      return {
        strong: searchResult.matches,
        near: searchResult.related,
        edges: searchResult.edges,
        quiet: new Set<string>(),
      };
    }
    if (!domainFocus) return null;
    const strong = new Set(
      graph.nodes.filter((node) => node.cluster === domainFocus).map((node) => node.id),
    );
    const near = new Set(strong);
    // Links out of the domain are the story; links inside it stay visible but unlabelled.
    const edges = new Set<string>();
    const quiet = new Set<string>();
    for (const edge of graph.edges) {
      const touches = strong.has(edge.source) || strong.has(edge.target);
      if (!touches) continue;
      if (ontologyMap.crossEdges.has(edge.id)) edges.add(edge.id);
      else quiet.add(edge.id);
      near.add(edge.source);
      near.add(edge.target);
    }
    return { strong, near, edges, quiet };
  }, [isOntology, searchResult, domainFocus, graph, ontologyMap.crossEdges]);

  const coreIds = React.useMemo(() => new Set(cores), [cores]);

  const visibleIds = React.useMemo(() => {
    if (isOntology) return null;
    if (isSimple) {
      if (simpleFilters.includes("all")) return null;
      return new Set(
        graph.nodes
          .filter((node) => nodeMatchesKindFilters(node, simpleFilters))
          .map((node) => node.id),
      );
    }
    return knowledgeVisibleIds(graph, knowledgeFilters);
  }, [isOntology, isSimple, simpleFilters, knowledgeFilters, graph]);

  const flowNodes: GalaxyFlowNode[] = React.useMemo(
    () =>
      live.map((node) => {
        const geo = geometry.get(node.id)!;
        const selected = node.id === selectedId;
        const highlighted = !focus && Boolean(highlight?.strong.has(node.id));
        const hop = focus?.hop1.has(node.id)
          ? 1
          : focus?.hop2.has(node.id)
            ? 2
            : !focus && highlight?.near.has(node.id) && !highlighted
              ? 1
              : null;
        const dimmed = focus
          ? !selected && hop === null
          : highlight
            ? !highlight.near.has(node.id)
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
            selectedConcept: selected || (highlighted && Boolean(searchResult)),
            hop,
            rank: rankById.get(node.id),
            displayLabel: displayName(node, overlay),
            core: isOntology && mapStyle !== "hierarchy" && coreIds.has(node.id),
          },
          zIndex: selected || highlighted
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
      highlight,
      searchResult,
      isOntology,
      mapStyle,
      coreIds,
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
        const crossDomain = isOntology && ontologyMap.crossEdges.has(edge.id);
        const emphasized = focus
          ? focus.edges1.has(edge.id)
          : highlight
            ? highlight.edges.has(edge.id)
            : Boolean(visibleIds) && touchesFilter;
        const secondary = Boolean(focus?.edges2.has(edge.id));
        const dimmed = focus
          ? !emphasized && !secondary
          : highlight
            ? !emphasized && !highlight.quiet.has(edge.id)
            : !touchesFilter;
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
            labelVisible: labelsVisible || (crossDomain && !highlight),
            dimmed,
            emphasized,
            secondary,
            curvature: placement.curvature,
            labelT: placement.labelT,
            glow: mode === "knowledge",
            motionEnabled,
            crossDomain,
          },
          zIndex: emphasized ? 4 : crossDomain ? 3 : secondary ? 2 : 0,
        };
      }),
    [
      graph.edges,
      isOntology,
      ontologyMap.crossEdges,
      highlight,
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
    setDomainFocus(null);
    setSearch("");
    setMode(next);
  }

  function focusDomain(next: string | null) {
    setSelectedId(null);
    setSearch("");
    setDomainFocus(next);
    const ids = next
      ? graph.nodes.filter((node) => node.cluster === next).map((node) => ({ id: node.id }))
      : undefined;
    window.setTimeout(() => {
      void fitView({ nodes: ids, padding: next ? 0.35 : 0.1, duration: 450 });
    }, 30);
  }

  const domainCounts = React.useMemo(() => {
    const counts = new Map<string, number>();
    for (const node of ontologyMap.graph.nodes) {
      counts.set(node.cluster, (counts.get(node.cluster) ?? 0) + 1);
    }
    return counts;
  }, [ontologyMap.graph.nodes]);

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
            {isOntology ? (
              <label className="relative mr-1 shrink-0">
                <span className="sr-only">Search the ontology</span>
                <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                <input
                  type="search"
                  value={search}
                  placeholder="Search ontology — try SUV, Dealer, Revenue"
                  className="ontology-search"
                  onChange={(event) => {
                    setSelectedId(null);
                    setDomainFocus(null);
                    setSearch(event.target.value);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Escape") setSearch("");
                    if (event.key === "Enter" && searchResult?.matches.size) {
                      const ids = [...searchResult.related].map((id) => ({ id }));
                      void fitView({ nodes: ids, padding: 0.25, duration: 450 });
                    }
                  }}
                />
              </label>
            ) : null}
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
            {layout === "knowledge" ||
            layout === "grouped" ||
            layout === "ontology" ? (
              <ToggleButton
                active={showZones}
                hint={
                  isOntology
                    ? "Outline each business domain as a community."
                    : "Shade the area each group occupies."
                }
                onClick={() => setShowZones((value) => !value)}
              >
                {isOntology ? "Domains" : "Groups"}
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
          {isOntology ? (
            <>
              <div
                className="flex shrink-0 items-center gap-1"
                role="group"
                aria-label="Business domains"
              >
                <CategoryPill
                  label="All"
                  count={ontologyMap.graph.nodes.length}
                  active={domainFocus === null}
                  hint="Show every business domain."
                  onClick={() => focusDomain(null)}
                />
                {ontologyMap.domains.map((domain) => (
                  <CategoryPill
                    key={domain.id}
                    label={domain.label}
                    count={domainCounts.get(domain.id) ?? 0}
                    color={domain.color}
                    active={domainFocus === domain.id}
                    hint={domain.hint}
                    onClick={() =>
                      focusDomain(domainFocus === domain.id ? null : domain.id)
                    }
                  />
                ))}
              </div>
              <ToolbarDivider />
              <SegmentGroup
                label="Layout"
                items={MAP_STYLES}
                value={mapStyle}
                onChange={(value) => {
                  setSelectedId(null);
                  setMapStyle(value);
                }}
              />
            </>
          ) : isSimple ? (
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
          {domainsVisible ? (
            <DomainLayer
              clusters={graph.clusters}
              nodes={live}
              focusId={searchResult ? null : domainFocus}
            />
          ) : null}
          <Panel position="top-left" className="m-3">
            <div className="galaxy-panel rounded-2xl border px-3 py-2 text-[11px] shadow-lg backdrop-blur-xl">
              <div className="flex items-center gap-2 font-semibold tracking-tight">
                <activeMode.icon className="size-3.5" />
                {activeMode.label} ·{" "}
                {isOntology ? `${ontologyMap.domains.length} domains · ` : null}
                {graph.metadata.nodeCount} concepts ·{" "}
                {isOntology
                  ? `${ontologyMap.crossEdges.size} cross-domain links`
                  : `${graph.metadata.edgeCount} relationships`}
              </div>
              <p className="galaxy-panel__muted mt-1 max-w-[20rem]">
                {selectedNode
                  ? mode === "knowledge"
                    ? `${selectedNode.label} · ${focus?.hop1.size ?? 0} direct, ${focus?.hop2.size ?? 0} two steps away`
                    : `${selectedNode.label} · ${focus?.hop1.size ?? 0} direct relationships`
                  : searchResult
                    ? searchResult.matches.size
                      ? `${searchResult.matches.size} match${searchResult.matches.size === 1 ? "" : "es"} · ${searchResult.related.size - searchResult.matches.size} connected concepts on the way to the core`
                      : `No concept matches “${search.trim()}”`
                    : isOntology && domainFocus
                      ? `${domainLabel.get(domainFocus)} domain · ${highlight ? highlight.near.size - highlight.strong.size : 0} concepts in other domains connect to it`
                      : MODE_HINT[mode]}
              </p>
            </div>
          </Panel>
          <Panel position="top-right" className="m-3">
            {isOntology ? (
              <OntologyLegend
                style={mapStyle}
                cores={cores.map((id) => nodeById.get(id)?.label ?? id)}
                bridges={ontologyMap.bridges.slice(0, 4).map((bridge) => ({
                  label: `${domainLabel.get(bridge.from)} ↔ ${domainLabel.get(bridge.to)}`,
                  count: bridge.count,
                }))}
              />
            ) : (
              <Legend mode={mode} metric={metric} />
            )}
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

function OntologyLegend({
  style,
  cores,
  bridges,
}: {
  style: OntologyMapStyle;
  cores: string[];
  bridges: Array<{ label: string; count: number }>;
}) {
  return (
    <div className="galaxy-panel max-w-[15rem] rounded-2xl border px-3 py-2 text-[10px] shadow-lg backdrop-blur-xl">
      <p className="mb-1 font-semibold">Core business concepts</p>
      <p className="galaxy-panel__muted mb-1.5">
        {style === "centrality"
          ? "Bigger and nearer the middle = more central"
          : "Haloed = most connected across the map"}
      </p>
      <ol className="mb-2 space-y-0.5">
        {cores.map((label, index) => (
          <li key={label} className="flex gap-1.5">
            <span className="galaxy-panel__muted tabular-nums">{index + 1}.</span>
            <span className="font-medium">{label}</span>
          </li>
        ))}
      </ol>
      {bridges.length ? (
        <>
          <p className="mb-1 font-semibold">How domains connect</p>
          <ul className="mb-2 space-y-0.5">
            {bridges.map((bridge) => (
              <li key={bridge.label} className="galaxy-panel__muted flex justify-between gap-2">
                <span>{bridge.label}</span>
                <span className="tabular-nums">{bridge.count}</span>
              </li>
            ))}
          </ul>
        </>
      ) : null}
      <div className="flex flex-col gap-1">
        <span className="galaxy-panel__muted inline-flex items-center gap-1.5">
          <span className="h-0.5 w-4 rounded-full" style={{ background: CROSS_DOMAIN_COLOR }} />
          Connects two domains
        </span>
        <span className="galaxy-panel__muted inline-flex items-center gap-1.5">
          <span className="h-px w-4 rounded-full bg-muted-foreground/60" />
          Within one domain
        </span>
      </div>
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
