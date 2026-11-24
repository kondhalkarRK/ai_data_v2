import { memo, useMemo } from "react";
import { useStore, type ReactFlowState } from "@xyflow/react";
import { convexHull, type RFNode } from "@/lib/layouts";
import type { ClusterMeta } from "@/lib/types";

interface ClusterZonesProps {
  clusters: ClusterMeta[];
  activeClusters: Set<string>;
  enabled: boolean;
}

function ClusterZonesComponent({
  clusters,
  activeClusters,
  enabled,
}: ClusterZonesProps) {
  const nodes = useStore((s: ReactFlowState) => s.nodes as RFNode[]);
  const transform = useStore((s: ReactFlowState) => s.transform);

  const zones = useMemo(() => {
    if (!enabled) return [];
    const [tx, ty, zoom] = transform;
    return clusters
      .filter((c) => activeClusters.has(c.id) && c.id !== "Domain")
      .map((c) => {
        const members = nodes.filter((n) => n.data.cluster === c.id && !n.hidden);
        if (members.length < 2) return null;
        const pts = members.map((n) => {
          const w = typeof n.measured?.width === "number" ? n.measured.width : 48;
          const h = typeof n.measured?.height === "number" ? n.measured.height : 48;
          return {
            x: n.position.x + w / 2,
            y: n.position.y + h / 2,
          };
        });
        const hull = convexHull(pts);
        if (hull.length < 2) return null;
        const pad = 36;
        // Expand hull slightly
        const cx = hull.reduce((s, p) => s + p.x, 0) / hull.length;
        const cy = hull.reduce((s, p) => s + p.y, 0) / hull.length;
        const expanded = hull.map((p) => {
          const dx = p.x - cx;
          const dy = p.y - cy;
          const len = Math.hypot(dx, dy) || 1;
          return {
            x: p.x + (dx / len) * pad,
            y: p.y + (dy / len) * pad,
          };
        });
        const screen = expanded.map((p) => ({
          x: p.x * zoom + tx,
          y: p.y * zoom + ty,
        }));
        const d =
          screen
            .map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
            .join(" ") + " Z";
        const label = {
          x: cx * zoom + tx,
          y: cy * zoom + ty - 28 * zoom,
        };
        return { id: c.id, color: c.color, d, label: c.label, labelPos: label };
      })
      .filter(Boolean) as {
      id: string;
      color: string;
      d: string;
      label: string;
      labelPos: { x: number; y: number };
    }[];
  }, [activeClusters, clusters, enabled, nodes, transform]);

  if (!enabled || zones.length === 0) return null;

  return (
    <svg className="cluster-layer" aria-hidden>
      {zones.map((z) => (
        <g key={z.id}>
          <path
            d={z.d}
            fill={z.color}
            fillOpacity={0.08}
            stroke={z.color}
            strokeOpacity={0.55}
            strokeWidth={1.5}
            strokeDasharray="6 5"
          />
          <text
            x={z.labelPos.x}
            y={z.labelPos.y}
            textAnchor="middle"
            className="cluster-label"
            fill={z.color}
          >
            {z.label.toUpperCase()}
          </text>
        </g>
      ))}
    </svg>
  );
}

export const ClusterZones = memo(ClusterZonesComponent);
