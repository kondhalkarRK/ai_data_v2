"use client";

import type { OntologyNode as OntologyNodeContract, OntologySnapshot } from "@nql/shared-types";
import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import dagre from "dagre";
import {
  Eye,
  EyeOff,
  GitBranch,
  Network,
  Orbit,
  Search,
} from "lucide-react";
import * as React from "react";

import { NodeDrawer } from "@/components/ontology/node-drawer";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type LayoutMode = "force" | "centrality" | "hierarchy";
type GraphNode = Node<OntologyNodeContract, "ontology">;

const NODE_WIDTH = 132;
const NODE_HEIGHT = 64;

const CLUSTER_CENTRES: Record<string, { x: number; y: number }> = {
  Domain: { x: 560, y: 50 },
  Facts: { x: 280, y: 250 },
  Dimensions: { x: 820, y: 250 },
  Entities: { x: 250, y: 560 },
  Measures: { x: 840, y: 560 },
  Metrics: { x: 560, y: 740 },
  Other: { x: 560, y: 400 },
};

function nodeRadius(node: OntologyNodeContract, centrality = false): number {
  const base =
    node.kind === "domain" ? 26 : node.kind === "entity" ? 21 : node.kind === "table" ? 19 : 16;
  return Math.min(42, base + node.degree * (centrality ? 2.4 : 1.2));
}

function layoutClustered(snapshot: OntologySnapshot, centrality: boolean): GraphNode[] {
  const groups = new Map<string, OntologyNodeContract[]>();
  for (const node of snapshot.nodes) {
    groups.set(node.cluster, [...(groups.get(node.cluster) ?? []), node]);
  }

  return snapshot.nodes.map((node) => {
    const peers = groups.get(node.cluster) ?? [node];
    const index = peers.findIndex((peer) => peer.id === node.id);
    const angle = (index / peers.length) * Math.PI * 2 - Math.PI / 2;
    const centre = CLUSTER_CENTRES[node.cluster] ?? { x: 560, y: 400 };
    const orbit = Math.max(76, Math.min(180, 40 + peers.length * 17));
    const radius = nodeRadius(node, centrality);
    return {
      id: node.id,
      type: "ontology",
      data: node,
      position: {
        x: centre.x + Math.cos(angle) * orbit - NODE_WIDTH / 2,
        y: centre.y + Math.sin(angle) * orbit - NODE_HEIGHT / 2,
      },
      style: { width: NODE_WIDTH, height: NODE_HEIGHT + Math.max(0, radius - 18) },
    };
  });
}

function layoutHierarchy(snapshot: OntologySnapshot): GraphNode[] {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: "TB", nodesep: 42, ranksep: 88, marginx: 36, marginy: 36 });
  for (const node of snapshot.nodes) {
    graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const edge of snapshot.edges) graph.setEdge(edge.source, edge.target);
  dagre.layout(graph);

  return snapshot.nodes.map((node) => {
    const position = graph.node(node.id) as { x: number; y: number };
    return {
      id: node.id,
      type: "ontology",
      data: node,
      position: { x: position.x - NODE_WIDTH / 2, y: position.y - NODE_HEIGHT / 2 },
      style: { width: NODE_WIDTH, height: NODE_HEIGHT },
    };
  });
}

function graphEdges(snapshot: OntologySnapshot): Edge[] {
  return snapshot.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: edge.kind === "relationship" ? edge.label : undefined,
    type: "straight",
    markerEnd:
      edge.kind === "relationship"
        ? { type: MarkerType.ArrowClosed, width: 12, height: 12 }
        : undefined,
    style: {
      stroke: "#94a3b8",
      strokeWidth: edge.kind === "relationship" ? 1.4 : 1,
      opacity: edge.kind === "dependency" ? 0.22 : 0.55,
    },
  }));
}

function OntologyGraphNode({ data, selected }: NodeProps<GraphNode>) {
  const radius = nodeRadius(data);
  return (
    <div
      className={cn(
        "flex h-full w-full flex-col items-center justify-center rounded-full border bg-surface-raised px-2 text-center shadow-[var(--shadow-card)] transition-[opacity,transform,box-shadow]",
        selected && "scale-105 shadow-[var(--shadow-raised)]",
        data.dimmed && "opacity-15",
      )}
      style={{ borderColor: data.clusterColor, minWidth: radius * 2 }}
    >
      <span
        className="mb-1 size-2 rounded-full"
        style={{ backgroundColor: data.clusterColor }}
        aria-hidden="true"
      />
      <span className="line-clamp-2 text-[10px] font-medium leading-tight">{data.label}</span>
    </div>
  );
}

const NODE_TYPES = { ontology: OntologyGraphNode };

export function OntologyBrowser({ snapshot }: { snapshot: OntologySnapshot }) {
  return (
    <ReactFlowProvider>
      <OntologyBrowserInner snapshot={snapshot} />
    </ReactFlowProvider>
  );
}

function OntologyBrowserInner({ snapshot }: { snapshot: OntologySnapshot }) {
  const flow = useReactFlow();
  const [layout, setLayout] = React.useState<LayoutMode>("force");
  const [zones, setZones] = React.useState(true);
  const [query, setQuery] = React.useState("");
  const [activeClusters, setActiveClusters] = React.useState<Set<string>>(
    () => new Set(snapshot.clusters.map((cluster) => cluster.id)),
  );
  const [selected, setSelected] = React.useState<OntologyNodeContract | null>(null);

  const nodes = React.useMemo(() => {
    const positioned =
      layout === "hierarchy"
        ? layoutHierarchy(snapshot)
        : layoutClustered(snapshot, layout === "centrality");
    const normalizedQuery = query.trim().toLowerCase();
    return positioned.map((node) => {
      const searchText = [
        node.data.label,
        node.data.id,
        node.data.description,
        ...node.data.synonyms,
        ...node.data.tables,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      const dimmed =
        !activeClusters.has(node.data.cluster) ||
        (normalizedQuery.length > 0 && !searchText.includes(normalizedQuery));
      return { ...node, data: { ...node.data, dimmed } };
    });
  }, [activeClusters, layout, query, snapshot]);

  const edges = React.useMemo(() => {
    const visible = new Set(
      nodes.filter((node) => !node.data.dimmed).map((node) => node.id),
    );
    return graphEdges(snapshot).map((edge) => ({
      ...edge,
      hidden: !visible.has(edge.source) || !visible.has(edge.target),
    }));
  }, [nodes, snapshot]);

  React.useEffect(() => {
    const timer = window.setTimeout(() => flow.fitView({ padding: 0.16, duration: 250 }), 0);
    return () => window.clearTimeout(timer);
  }, [flow, layout, snapshot]);

  function toggleCluster(cluster: string) {
    setActiveClusters((current) => {
      const next = new Set(current);
      if (next.has(cluster)) next.delete(cluster);
      else next.add(cluster);
      return next;
    });
  }

  const visibleCount = nodes.filter((node) => !node.data.dimmed).length;

  return (
    <section className="relative flex min-h-[42rem] flex-col overflow-hidden rounded-[var(--radius-card)] border border-border bg-surface-raised">
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2.5">
        <div className="relative min-w-[15rem] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search ontology — try 'premium' or 'vehicle'"
            aria-label="Search ontology"
            className="pl-9"
          />
        </div>
        <div className="flex rounded-[var(--radius-control)] border border-border p-0.5">
          {(
            [
              ["force", "Force", Orbit],
              ["centrality", "Centrality", Network],
              ["hierarchy", "Hierarchy", GitBranch],
            ] as const
          ).map(([id, label, Icon]) => (
            <Button
              key={id}
              variant={layout === id ? "primary" : "ghost"}
              size="sm"
              onClick={() => setLayout(id)}
              aria-pressed={layout === id}
            >
              <Icon />
              <span className="hidden sm:inline">{label}</span>
            </Button>
          ))}
        </div>
        <Button
          variant={zones ? "secondary" : "ghost"}
          size="sm"
          onClick={() => setZones((value) => !value)}
          aria-pressed={zones}
        >
          {zones ? <Eye /> : <EyeOff />}
          Cluster zones
        </Button>
      </div>

      <div className="flex flex-wrap gap-1.5 border-b border-border px-3 py-2">
        {snapshot.clusters.map((cluster) => {
          const active = activeClusters.has(cluster.id);
          return (
            <button
              key={cluster.id}
              type="button"
              onClick={() => toggleCluster(cluster.id)}
              aria-pressed={active}
              className="rounded-full border px-3 py-1 text-xs font-medium transition-opacity"
              style={{
                color: cluster.color,
                borderColor: `${cluster.color}66`,
                backgroundColor: active ? `${cluster.color}12` : "transparent",
                opacity: active ? 1 : 0.42,
              }}
            >
              {cluster.label}
            </button>
          );
        })}
      </div>

      <div className="relative min-h-0 flex-1">
        <div className="absolute left-3 top-3 z-10 rounded-[var(--radius-control)] border border-border bg-background/90 p-3 font-mono text-2xs leading-5 shadow-[var(--shadow-card)] backdrop-blur">
          <p><span className="mr-2 inline-block size-1.5 rounded-full bg-success" />live</p>
          <p>nodes {visibleCount}/{snapshot.metadata.nodeCount}</p>
          <p>edges {snapshot.metadata.edgeCount}</p>
          <p>graph build {snapshot.metadata.buildMs}ms</p>
          <p className="text-muted-foreground">source: semantic snapshot</p>
        </div>

        {zones && layout !== "hierarchy" ? (
          <div className="pointer-events-none absolute inset-0 opacity-40" aria-hidden="true">
            {snapshot.clusters.map((cluster, index) => (
              <div
                key={cluster.id}
                className="absolute rounded-[50%] border border-dashed"
                style={{
                  borderColor: cluster.color,
                  backgroundColor: `${cluster.color}08`,
                  width: "28%",
                  height: "34%",
                  left: `${12 + (index % 3) * 28}%`,
                  top: `${12 + Math.floor(index / 3) * 42}%`,
                }}
              />
            ))}
          </div>
        ) : null}

        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          nodesDraggable
          nodesConnectable={false}
          elementsSelectable
          minZoom={0.18}
          maxZoom={2.5}
          fitView
          onNodeClick={(_, node) => {
            if (!node.data.dimmed) setSelected(node.data);
          }}
          onPaneClick={() => setSelected(null)}
          proOptions={{ hideAttribution: true }}
          aria-label="Semantic ontology graph"
        >
          <Background color="#94a3b8" gap={24} size={0.5} />
          <Controls showInteractive={false} position="top-left" />
        </ReactFlow>

        <p className="pointer-events-none absolute bottom-3 left-1/2 z-10 -translate-x-1/2 rounded-full border border-border bg-background/90 px-3 py-1.5 text-xs text-muted-foreground shadow-[var(--shadow-card)]">
          Click a node to inspect · scroll to zoom · drag to pan
        </p>
        <NodeDrawer node={selected} onClose={() => setSelected(null)} />
      </div>
    </section>
  );
}
