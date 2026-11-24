import {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
} from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Edge,
  type Node,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { motion } from "framer-motion";

import { OntologyNode } from "@/components/OntologyNode";
import { NodeDrawer } from "@/components/NodeDrawer";
import { ClusterZones } from "@/components/ClusterZones";
import {
  applyLayout,
  toReactFlowElements,
  type RFEdge,
  type RFNode,
} from "@/lib/layouts";
import type {
  LayoutMode,
  OntologyGraph,
  OntologyNodeData,
} from "@/lib/types";

const nodeTypes: NodeTypes = {
  ontology: OntologyNode as unknown as NodeTypes[string],
};

interface OntologyBrowserProps {
  graph: OntologyGraph;
  buildMs: number;
  packLabel: string;
}

function OntologyBrowserInner({ graph, buildMs, packLabel }: OntologyBrowserProps) {
  const { fitView, zoomIn, zoomOut } = useReactFlow();
  const [layoutMode, setLayoutMode] = useState<LayoutMode>("force");
  const [clusterZones, setClusterZones] = useState(true);
  const [query, setQuery] = useState("");
  const [activeClusters, setActiveClusters] = useState<Set<string>>(
    () => new Set(graph.clusters.map((c) => c.id)),
  );
  const [selected, setSelected] = useState<OntologyNodeData | null>(null);
  const [focusId, setFocusId] = useState<string | null>(null);
  const builtRef = useRef(false);

  const base = useMemo(() => toReactFlowElements(graph), [graph]);

  const prepare = useCallback(
    (mode: LayoutMode, clusters: Set<string>, q: string, focus: string | null) => {
      const qLower = q.trim().toLowerCase();
      let nodes: RFNode[] = base.nodes
        .filter((n) => clusters.has(n.data.cluster))
        .map((n) => {
          const match =
            !qLower ||
            n.data.label.toLowerCase().includes(qLower) ||
            n.data.synonyms.some((s) => s.toLowerCase().includes(qLower)) ||
            n.data.tables.some((t) => t.toLowerCase().includes(qLower));
          return {
            ...n,
            hidden: Boolean(qLower) && !match,
            data: { ...n.data },
          };
        });

      const visibleIds = new Set(nodes.filter((n) => !n.hidden).map((n) => n.id));
      let edges: RFEdge[] = base.edges.filter(
        (e) => visibleIds.has(e.source) && visibleIds.has(e.target),
      );

      nodes = applyLayout(
        mode,
        nodes.filter((n) => !n.hidden),
        edges,
      );

      // Re-merge hidden nodes (keep off-canvas) so React Flow identity stays stable
      const laid = new Map(nodes.map((n) => [n.id, n]));
      nodes = base.nodes.map((n) => {
        if (!clusters.has(n.data.cluster)) {
          return { ...n, hidden: true };
        }
        const positioned = laid.get(n.id);
        if (!positioned) return { ...n, hidden: true };
        return positioned;
      });

      if (focus) {
        const ego = new Set<string>([focus]);
        for (const e of base.edges) {
          if (e.source === focus) ego.add(e.target);
          if (e.target === focus) ego.add(e.source);
        }
        nodes = nodes.map((n) => ({
          ...n,
          data: { ...n.data, dimmed: !ego.has(n.id) },
        }));
        edges = edges.map((e) => {
          const hot = ego.has(e.source) && ego.has(e.target);
          return {
            ...e,
            animated: hot && (e.source === focus || e.target === focus),
            style: {
              ...e.style,
              stroke: hot ? "#2563eb" : "#cbd5e1",
              strokeWidth: hot ? 2.2 : 1,
              opacity: hot ? 0.9 : 0.15,
            },
          };
        });
      }

      return { nodes, edges };
    },
    [base.edges, base.nodes],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState<Node<OntologyNodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  const relayout = useCallback(
    (mode: LayoutMode, clusters: Set<string>, q: string, focus: string | null) => {
      const next = prepare(mode, clusters, q, focus);
      setNodes(next.nodes);
      setEdges(next.edges);
      requestAnimationFrame(() => {
        fitView({ padding: 0.18, duration: 450 });
      });
    },
    [fitView, prepare, setEdges, setNodes],
  );

  useEffect(() => {
    setActiveClusters(new Set(graph.clusters.map((c) => c.id)));
    setSelected(null);
    setFocusId(null);
    setQuery("");
    builtRef.current = false;
  }, [graph]);

  useEffect(() => {
    relayout(layoutMode, activeClusters, query, focusId);
    builtRef.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph, layoutMode]);

  const visibleCount = nodes.filter((n) => !n.hidden).length;

  const onNodeClick = useCallback(
    (_: MouseEvent, node: Node<OntologyNodeData>) => {
      setSelected(node.data);
      setFocusId(node.id);
      const next = prepare(layoutMode, activeClusters, query, node.id);
      setNodes(next.nodes);
      setEdges(next.edges);
    },
    [activeClusters, layoutMode, prepare, query, setEdges, setNodes],
  );

  const onPaneClick = useCallback(() => {
    setSelected(null);
    setFocusId(null);
    relayout(layoutMode, activeClusters, query, null);
  }, [activeClusters, layoutMode, query, relayout]);

  const toggleCluster = (id: string) => {
    setActiveClusters((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      // defer layout
      queueMicrotask(() => relayout(layoutMode, next, query, focusId));
      return next;
    });
  };

  const applySearch = (value: string) => {
    setQuery(value);
    relayout(layoutMode, activeClusters, value, focusId);
  };

  return (
    <div className="browser-shell">
      <div className="browser-toolbar">
        <div className="browser-title">
          <div className="browser-title__icon" aria-hidden>
            ◉
          </div>
          <div>
            <h1>Ontology Browser</h1>
            <p>SEMANTIC CORE · KNOWLEDGE GRAPH</p>
          </div>
        </div>

        <div className="viewport-tools">
          <button type="button" className="round-btn" onClick={() => zoomIn({ duration: 200 })}>
            +
          </button>
          <button type="button" className="round-btn" onClick={() => zoomOut({ duration: 200 })}>
            −
          </button>
          <button
            type="button"
            className="round-btn"
            onClick={() => fitView({ padding: 0.18, duration: 400 })}
            title="Fit"
          >
            ⛶
          </button>
          <button
            type="button"
            className="round-btn"
            onClick={() => relayout(layoutMode, activeClusters, query, focusId)}
            title="Refresh layout"
          >
            ⟳
          </button>
        </div>

        <label className="search-field">
          <span aria-hidden>⌕</span>
          <input
            value={query}
            onChange={(e) => applySearch(e.target.value)}
            placeholder="Search ontology — try a table, synonym, or entity"
          />
        </label>

        <div className="layout-toggle" role="group" aria-label="Layout mode">
          {(["force", "centrality", "hierarchy"] as LayoutMode[]).map((mode) => (
            <button
              key={mode}
              type="button"
              className={layoutMode === mode ? "is-active" : ""}
              onClick={() => setLayoutMode(mode)}
            >
              {mode[0].toUpperCase() + mode.slice(1)}
            </button>
          ))}
        </div>

        <label className="cluster-switch">
          <input
            type="checkbox"
            checked={clusterZones}
            onChange={(e) => setClusterZones(e.target.checked)}
          />
          <span>Cluster zones</span>
        </label>
      </div>

      <div className="cluster-chips">
        {graph.clusters.map((c) => {
          const on = activeClusters.has(c.id);
          return (
            <button
              key={c.id}
              type="button"
              className={`cluster-chip${on ? " is-on" : ""}`}
              style={{ "--chip": c.color } as React.CSSProperties}
              onClick={() => toggleCluster(c.id)}
            >
              <span className="cluster-chip__dot" />
              {c.label}
            </button>
          );
        })}
      </div>

      <div className="graph-stage">
        <motion.div
          className="stats-card"
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div>
            <span className="live-dot" /> live
          </div>
          <div>
            nodes {visibleCount}/{graph.nodes.length}
          </div>
          <div>edges {edges.length}</div>
          <div>graph build {buildMs}ms</div>
          <div className="muted">source: {packLabel}</div>
        </motion.div>

        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          onNodeClick={onNodeClick}
          onPaneClick={onPaneClick}
          fitView
          minZoom={0.15}
          maxZoom={2.2}
          onlyRenderVisibleElements
          proOptions={{ hideAttribution: true }}
          defaultEdgeOptions={{ type: "default" }}
        >
          <Background gap={22} size={1} color="#e2e8f0" />
          <Controls showInteractive={false} />
          <MiniMap
            pannable
            zoomable
            nodeColor={(n) => (n.data as OntologyNodeData)?.clusterColor || "#94a3b8"}
            maskColor="rgba(248,250,252,.75)"
          />
          <ClusterZones
            clusters={graph.clusters}
            activeClusters={activeClusters}
            enabled={clusterZones}
          />
        </ReactFlow>

        <div className="hint-pill">
          Click a node to focus its egonet · scroll to zoom · drag to pan
        </div>

        <NodeDrawer
          node={selected}
          onClose={() => {
            setSelected(null);
            setFocusId(null);
            relayout(layoutMode, activeClusters, query, null);
          }}
        />
      </div>
    </div>
  );
}

function OntologyBrowser(props: OntologyBrowserProps) {
  return (
    <ReactFlowProvider>
      <OntologyBrowserInner {...props} />
    </ReactFlowProvider>
  );
}

export default memo(OntologyBrowser);
