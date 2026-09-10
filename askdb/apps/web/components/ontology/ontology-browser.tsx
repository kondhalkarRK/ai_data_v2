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
import {
  Binary,
  GitBranch,
  Network,
  Orbit,
  Search,
  Share2,
  Sparkles,
  Target,
  Waypoints,
} from "lucide-react";
import * as React from "react";

import { ClusterLayer } from "@/components/ontology/cluster-layer";
import { GalaxyEdge, EDGE_STYLES, type GalaxyFlowEdge } from "@/components/ontology/galaxy-edge";
import { GalaxyNode, type GalaxyFlowNode } from "@/components/ontology/galaxy-node";
import "@/components/ontology/galaxy-styles.css";
import { NodeDrawer } from "@/components/ontology/node-drawer";
import { ParticleField } from "@/components/ontology/particle-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { hopNeighborhood } from "@/lib/ontology/graph-metrics";
import {
  edgeVisualKind,
  layoutGalaxy,
  type CentralityMetric,
  type GalaxyMode,
  type PositionedNode,
} from "@/lib/ontology/layouts";
import { cn } from "@/lib/utils";

const nodeTypes: NodeTypes = { galaxy: GalaxyNode };
const edgeTypes: EdgeTypes = { galaxy: GalaxyEdge };

const MODES: ReadonlyArray<{
  id: GalaxyMode;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}> = [
  { id: "network", label: "Network", icon: Network },
  { id: "centrality", label: "Centrality", icon: Target },
  { id: "hierarchy", label: "Hierarchy", icon: GitBranch },
  { id: "lineage", label: "Lineage", icon: Waypoints },
  { id: "constellation", label: "Constellation", icon: Orbit },
];

const METRICS: ReadonlyArray<{ id: CentralityMetric; label: string }> = [
  { id: "degree", label: "Degree" },
  { id: "betweenness", label: "Betweenness" },
  { id: "pagerank", label: "PageRank" },
];

export function OntologyBrowser({ snapshot }: { snapshot: OntologySnapshot }) {
  return (
    <ReactFlowProvider>
      <OntologyBrowserInner snapshot={snapshot} />
    </ReactFlowProvider>
  );
}

function OntologyBrowserInner({ snapshot }: { snapshot: OntologySnapshot }) {
  const { fitView, setCenter, getNode } = useReactFlow();
  const [mode, setMode] = React.useState<GalaxyMode>("constellation");
  const [metric, setMetric] = React.useState<CentralityMetric>("pagerank");
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [search, setSearch] = React.useState("");
  const [pulseId, setPulseId] = React.useState<string | null>(null);
  const [activeCluster, setActiveCluster] = React.useState<string | null>(null);
  const [showClusters, setShowClusters] = React.useState(true);

  const positioned = React.useMemo(
    () => layoutGalaxy(snapshot, mode, metric),
    [snapshot, mode, metric],
  );

  const nodeById = React.useMemo(() => {
    const map = new Map(snapshot.nodes.map((node) => [node.id, node]));
    return map;
  }, [snapshot.nodes]);

  const focus = React.useMemo(() => {
    if (!selectedId) return null;
    const links = snapshot.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
    }));
    const one = hopNeighborhood(selectedId, links, 1);
    const two = hopNeighborhood(selectedId, links, 2);
    return { one, two };
  }, [selectedId, snapshot.edges]);

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
        if (hop === 2 && !focus.one.nodes.has(node.id)) {
          // keep 2-hop visible but slightly quieter via opacity in CSS only when dimmed false
        }
      }
      if (activeCluster && node.cluster !== activeCluster && node.id !== selectedId) {
        dimmed = true;
      }
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
        },
        style: { width: size, height: size + 4 },
        zIndex: focused || pulseId === node.id ? 20 : dimmed ? 1 : 5,
      };
    });
  }, [positioned, focus, selectedId, pulseId, activeCluster]);

  const flowEdges: GalaxyFlowEdge[] = React.useMemo(() => {
    return snapshot.edges.map((edge) => {
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
      return {
        id: edge.id,
        type: "galaxy",
        source: edge.source,
        target: edge.target,
        data: {
          visualKind,
          label: edge.label || EDGE_STYLES[visualKind].label,
          dimmed,
          emphasized,
        },
        animated: emphasized,
        zIndex: emphasized ? 4 : 0,
      };
    });
  }, [snapshot.edges, nodeById, focus, activeCluster]);

  const selectedNode = selectedId ? (nodeById.get(selectedId) ?? null) : null;

  const relationshipCount = focus?.one.edges.size ?? 0;

  const searchHits = React.useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return [];
    return snapshot.nodes
      .filter((node) => {
        if (node.label.toLowerCase().includes(q) || node.id.toLowerCase().includes(q)) return true;
        return node.columns.some(
          (col) =>
            col.name.toLowerCase().includes(q) || col.displayName.toLowerCase().includes(q),
        );
      })
      .slice(0, 8);
  }, [search, snapshot.nodes]);

  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      void fitView({ padding: 0.22, duration: 650 });
    }, 40);
    return () => window.clearTimeout(timer);
  }, [mode, metric, snapshot, fitView]);

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

  const positionedForClusters: PositionedNode[] = positioned;

  return (
    <div className="semantic-galaxy relative flex h-[min(78vh,860px)] min-h-[560px] w-full flex-col">
      <ParticleField />

      <div className="galaxy-toolbar relative z-20 flex flex-wrap items-center gap-2 px-3 py-2.5">
        <div className="mr-1 flex items-center gap-2">
          <Sparkles className="size-3.5 text-info" aria-hidden="true" />
          <span className="text-xs font-semibold tracking-tight">Semantic Galaxy</span>
        </div>

        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Visualization mode">
          {MODES.map((item) => {
            const Icon = item.icon;
            const active = mode === item.id;
            return (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={active}
                className={cn(
                  "galaxy-chip inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium",
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

        {mode === "centrality" ? (
          <div className="flex gap-1">
            {METRICS.map((item) => (
              <button
                key={item.id}
                type="button"
                className={cn(
                  "galaxy-chip rounded-full px-2.5 py-1 text-[11px] font-medium",
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

        <div className="ml-auto flex min-w-[220px] max-w-sm flex-1 items-center gap-2">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search tables, columns…"
              className="h-8 border-border/60 bg-surface-raised/70 pl-8 text-xs backdrop-blur"
              aria-label="Semantic search"
            />
            <AnimatePresence>
              {searchHits.length > 0 ? (
                <motion.ul
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  className="absolute left-0 right-0 top-[calc(100%+6px)] z-30 overflow-hidden rounded-xl border border-border/70 bg-surface-raised/95 shadow-[var(--shadow-overlay)] backdrop-blur-xl"
                >
                  {searchHits.map((hit) => (
                    <li key={hit.id}>
                      <button
                        type="button"
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs hover:bg-muted/50"
                        onClick={() => {
                          setSearch("");
                          focusNode(hit.id);
                        }}
                      >
                        <span
                          className="size-2 shrink-0 rounded-full"
                          style={{ background: hit.clusterColor }}
                        />
                        <span className="truncate font-medium">{hit.label}</span>
                        <span className="ml-auto truncate font-mono text-[10px] text-muted-foreground">
                          {hit.kind}
                        </span>
                      </button>
                    </li>
                  ))}
                </motion.ul>
              ) : null}
            </AnimatePresence>
          </div>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-8 gap-1.5 text-xs"
            onClick={() => setShowClusters((value) => !value)}
          >
            <Share2 className="size-3.5" />
            {showClusters ? "Zones" : "Flat"}
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
              clusters={snapshot.clusters}
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
                <Binary className="size-3.5 text-success" />
                {snapshot.metadata.nodeCount} nodes · {snapshot.metadata.edgeCount} edges
              </div>
              {selectedId ? (
                <p className="mt-1 text-muted-foreground">
                  Focus · {relationshipCount} direct relations · 2-hop neighborhood
                </p>
              ) : (
                <p className="mt-1 text-muted-foreground">Click a node to enter Focus Graph</p>
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

        <NodeDrawer node={selectedNode} onClose={() => setSelectedId(null)} />
      </div>
    </div>
  );
}
