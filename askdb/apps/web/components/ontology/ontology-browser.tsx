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
import { AnimatePresence, motion } from "framer-motion";
import { Maximize2, Minimize2, Orbit, Search, Share2, Sparkles } from "lucide-react";
import * as React from "react";

import { ClusterLayer } from "@/components/ontology/cluster-layer";
import { GalaxyEdge, EDGE_STYLES, type GalaxyFlowEdge } from "@/components/ontology/galaxy-edge";
import { GalaxyNode, type GalaxyFlowNode } from "@/components/ontology/galaxy-node";
import "@/components/ontology/galaxy-styles.css";
import { NodeDrawer } from "@/components/ontology/node-drawer";
import { ParticleField } from "@/components/ontology/particle-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  JOURNEYS,
  deriveAssetContext,
  displayName,
  journeyNodeIds,
  matchesDiscoveryQuery,
  snapshotTrustRate,
  storyLabel,
  type ContextOverlay,
} from "@/lib/ontology/asset-context";
import { hopNeighborhood } from "@/lib/ontology/graph-metrics";
import {
  ONTOLOGY_KIND_FILTERS,
  nodeMatchesKindFilter,
  type OntologyKindFilter,
} from "@/lib/ontology/kind-filter";
import {
  edgeVisualKind,
  layoutGalaxy,
  type CentralityMetric,
  type GalaxyMode,
  type PositionedNode,
} from "@/lib/ontology/layouts";
import { conceptOnlySnapshot, mergeOntologyConcepts } from "@/lib/ontology/merge-concepts";
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

const DISCOVERY_HINTS = [
  "Revenue",
  "Sales",
  "Dealer",
  "Customer",
  "Claims",
  "Premium",
  "Vehicle",
  "Policy",
];

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
  const [search, setSearch] = React.useState("");
  const [pulseId, setPulseId] = React.useState<string | null>(null);
  const [activeCluster, setActiveCluster] = React.useState<string | null>(null);
  const [showClusters, setShowClusters] = React.useState(true);
  const [motionEnabled, setMotionEnabled] = React.useState(true);
  const [kindFilter, setKindFilter] = React.useState<OntologyKindFilter>("all");
  const [overlay, setOverlay] = React.useState<ContextOverlay>("business");
  const [journeyId, setJourneyId] = React.useState<string | null>(null);
  const [fullScreen, setFullScreen] = React.useState(false);

  const graph = React.useMemo(() => {
    const merged = mergeOntologyConcepts(snapshot);
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
      if (kindFilter !== "all") {
        const matches = nodeMatchesKindFilter(node, kindFilter);
        if (matches) {
          focused = focused || !focus;
        } else {
          dimmed = true;
          if (node.id !== selectedId) focused = false;
        }
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
    kindFilter,
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
      if (kindFilter !== "all") {
        const source = nodeById.get(edge.source);
        const target = nodeById.get(edge.target);
        if (kindFilter === "relationship") {
          emphasized = !dimmed;
        } else {
          const sourceMatch = source ? nodeMatchesKindFilter(source, kindFilter) : false;
          const targetMatch = target ? nodeMatchesKindFilter(target, kindFilter) : false;
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
  }, [graph.edges, nodeById, focus, activeCluster, kindFilter, motionEnabled, journeySet, overlay]);

  const selectedNode = selectedId ? (nodeById.get(selectedId) ?? null) : null;

  const relationshipCount = focus?.one.edges.size ?? 0;

  const searchHits = React.useMemo(() => {
    if (!search.trim()) return [];
    return graph.nodes.filter((node) => matchesDiscoveryQuery(node, search)).slice(0, 10);
  }, [search, graph.nodes]);

  const execStats = React.useMemo(() => {
    const metrics = graph.nodes.filter((node) => node.kind === "measure").length;
    const glossary = new Set(graph.nodes.flatMap((node) => node.synonyms)).size;
    return {
      concepts: graph.metadata.nodeCount,
      communities: graph.clusters.length,
      metrics,
      glossary,
      relationships: graph.metadata.edgeCount,
      trusted: snapshotTrustRate(graph),
    };
  }, [graph]);

  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      void fitView({ padding: 0.22, duration: 650 });
    }, 40);
    return () => window.clearTimeout(timer);
  }, [mode, metric, graph, fitView, fullScreen]);

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

  React.useEffect(() => {
    if (!fullScreen) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setFullScreen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fullScreen]);

  const positionedForClusters: PositionedNode[] = positioned;

  return (
    <div
      className={cn(
        "semantic-galaxy relative flex w-full flex-col",
        fullScreen
          ? "fixed inset-0 z-[80] h-dvh min-h-0 rounded-none"
          : "h-[min(88vh,980px)] min-h-[680px]",
      )}
      data-motion={motionEnabled ? "on" : "off"}
      data-mode={mode}
    >
      {motionEnabled ? <ParticleField /> : null}

      <div className="relative z-20 border-b border-border/50 bg-surface-raised/55 px-3 py-3 backdrop-blur-xl">
        <div className="mb-3 grid grid-cols-3 gap-2 sm:grid-cols-6">
          <ExecStat label="Concepts" value={String(execStats.concepts)} />
          <ExecStat label="Communities" value={String(execStats.communities)} />
          <ExecStat label="Metrics" value={String(execStats.metrics)} />
          <ExecStat label="Glossary" value={String(execStats.glossary)} />
          <ExecStat label="Relationships" value={String(execStats.relationships)} />
          <ExecStat label="Trusted" value={`${execStats.trusted}%`} />
        </div>
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search concepts, glossary, relationships…"
            className="h-11 border-border/60 bg-surface-raised/80 pl-10 text-sm shadow-sm backdrop-blur"
            aria-label="Discover assets"
          />
          <AnimatePresence>
            {searchHits.length > 0 ? (
              <motion.ul
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                className="absolute left-0 right-0 top-[calc(100%+8px)] z-40 max-h-72 overflow-auto rounded-xl border border-border/70 bg-surface-raised/98 shadow-[var(--shadow-overlay)] backdrop-blur-xl"
              >
                {searchHits.map((hit) => (
                  <li key={hit.id}>
                    <button
                      type="button"
                      className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-sm hover:bg-muted/50"
                      onClick={() => {
                        setSearch("");
                        setJourneyId(null);
                        focusNode(hit.id);
                      }}
                    >
                      <span
                        className="size-2 shrink-0 rounded-full"
                        style={{ background: hit.clusterColor }}
                      />
                      <span className="min-w-0">
                        <span className="block truncate font-medium">{displayName(hit, overlay)}</span>
                        <span className="block truncate text-[11px] text-muted-foreground">
                          {hit.domain} · {hit.kind}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </motion.ul>
            ) : null}
          </AnimatePresence>
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {DISCOVERY_HINTS.map((hint) => (
            <button
              key={hint}
              type="button"
              className="galaxy-chip rounded-full px-2.5 py-1 text-[11px] text-muted-foreground hover:bg-muted/40 hover:text-foreground"
              onClick={() => setSearch(hint)}
            >
              {hint}
            </button>
          ))}
        </div>
      </div>

      <div className="galaxy-toolbar relative z-20 space-y-2 px-3 py-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <div className="mr-1 flex items-center gap-2">
            <Sparkles className="size-3.5 text-info" aria-hidden="true" />
            <span className="text-xs font-semibold tracking-tight">Graph</span>
          </div>

          <div className="flex flex-wrap gap-1" role="tablist" aria-label="Map view">
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
                    "galaxy-chip galaxy-hint inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium",
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

          {mode === "network" ? (
            <div className="flex gap-1" role="tablist" aria-label="Influence metric">
              {METRICS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  data-hint={item.hint}
                  aria-label={`${item.label}. ${item.hint}`}
                  className={cn(
                    "galaxy-chip galaxy-hint rounded-full px-2.5 py-1 text-[11px] font-medium",
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
          ) : null}

          <div className="ml-auto flex items-center gap-1">
            <Button
              type="button"
              size="sm"
              className="galaxy-hint h-8 gap-1.5 text-xs"
              data-hint={
                fullScreen
                  ? "Exit full screen and return to the page layout."
                  : "Expand the graph to fill the screen for exploration."
              }
              aria-pressed={fullScreen}
              onClick={() => setFullScreen((value) => !value)}
            >
              {fullScreen ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}
              {fullScreen ? "Exit full screen" : "Full Screen"}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="galaxy-hint h-8 gap-1.5 text-xs"
              data-hint="Animate nodes and flowing relationship lines."
              aria-pressed={motionEnabled}
              aria-label={`Motion ${motionEnabled ? "on" : "off"}`}
              onClick={() => setMotionEnabled((value) => !value)}
            >
              Motion: {motionEnabled ? "ON" : "OFF"}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="galaxy-hint h-8 gap-1.5 text-xs"
              data-hint="Show or hide colored domain boundaries on the constellation map."
              onClick={() => setShowClusters((value) => !value)}
            >
              <Share2 className="size-3.5" />
              {showClusters ? "Zones" : "Flat"}
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-border/40 pt-2">
          <ToolbarSelect
            label="Labels"
            hint="Change names on the same map — business, technical, or governance language."
            value={overlay}
            onChange={(value) => setOverlay(value as ContextOverlay)}
            options={OVERLAYS.map((item) => ({ id: item.id, label: item.label, hint: item.hint }))}
          />
          <ToolbarSelect
            label="Show"
            hint="Focus the map on one asset type, such as measures or entities."
            value={kindFilter}
            onChange={(value) => setKindFilter(value as OntologyKindFilter)}
            options={ONTOLOGY_KIND_FILTERS}
          />
          <ToolbarSelect
            label="Story"
            hint="Highlight a curated business path, such as Revenue through Dealer and Region."
            value={journeyId ?? "none"}
            onChange={(value) => {
              const next = value === "none" ? null : value;
              setJourneyId(next);
              if (!next) return;
              const journey = JOURNEYS.find((item) => item.id === next);
              if (!journey) return;
              const ids = journeyNodeIds(graph, journey.seeds);
              if (ids[0]) focusNode(ids[0]);
            }}
            options={[
              { id: "none", label: "None", hint: "No guided path." },
              ...JOURNEYS.map((item) => ({
                id: item.id,
                label: item.label.replace(" journey", ""),
                hint: `Follow ${item.seeds.join(" → ")}.`,
              })),
            ]}
          />
        </div>
      </div>

      <div className="relative z-10 min-h-0 flex-1">
        <ReactFlow
          nodes={flowNodes}
          edges={flowEdges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
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

function ExecStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border/50 bg-surface-raised/70 px-2.5 py-2">
      <p className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-sm font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function ToolbarSelect({
  label,
  hint,
  value,
  onChange,
  options,
}: {
  label: string;
  hint: string;
  value: string;
  onChange: (value: string) => void;
  options: ReadonlyArray<{ id: string; label: string; hint?: string }>;
}) {
  const selected = options.find((item) => item.id === value);
  return (
    <label
      className="galaxy-hint inline-flex items-center gap-1.5 rounded-full border border-border/60 bg-surface-raised/70 px-2.5 py-1"
      data-hint={selected?.hint ?? hint}
    >
      <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
        {label}
      </span>
      <select
        value={value}
        aria-label={`${label}. ${hint}`}
        onChange={(event) => onChange(event.target.value)}
        className="max-w-[9.5rem] cursor-pointer bg-transparent text-[11px] font-medium outline-none"
      >
        {options.map((item) => (
          <option key={item.id} value={item.id} title={item.hint}>
            {item.label}
          </option>
        ))}
      </select>
    </label>
  );
}
