"use client";

import type { OntologyCluster } from "@nql/shared-types";
import { ViewportPortal } from "@xyflow/react";
import * as React from "react";

import { centroid, convexHull, expandHull, hullToPath, type Point } from "@/lib/ontology/hull";
import type { PositionedNode } from "@/lib/ontology/layouts";

export function ClusterLayer({
  clusters,
  nodes,
  activeCluster,
  onHover,
}: {
  clusters: OntologyCluster[];
  nodes: PositionedNode[];
  activeCluster: string | null;
  onHover: (clusterId: string | null) => void;
}) {
  const zones = React.useMemo(() => {
    return clusters
      .map((cluster) => {
        const members = nodes.filter((node) => node.cluster === cluster.id);
        if (!members.length) return null;
        const points: Point[] = members.map((node) => ({ x: node.x, y: node.y }));
        for (const node of members) {
          const pad = node.radius + 36;
          points.push(
            { x: node.x - pad, y: node.y },
            { x: node.x + pad, y: node.y },
            { x: node.x, y: node.y - pad },
            { x: node.x, y: node.y + pad },
          );
        }
        const hull = expandHull(convexHull(points), 28);
        const center = centroid(hull);
        return { cluster, path: hullToPath(hull), center };
      })
      .filter(Boolean) as Array<{
      cluster: OntologyCluster;
      path: string;
      center: Point;
    }>;
  }, [clusters, nodes]);

  return (
    <ViewportPortal>
      <svg
        className="pointer-events-none overflow-visible"
        style={{ position: "absolute", left: 0, top: 0, width: 1, height: 1, overflow: "visible" }}
        aria-hidden="true"
      >
        <defs>
          {clusters.map((cluster) => (
            <linearGradient
              key={cluster.id}
              id={`galaxy-grad-${cluster.id}`}
              x1="0%"
              y1="0%"
              x2="100%"
              y2="100%"
            >
              <stop offset="0%" stopColor={cluster.color} stopOpacity="0.55" />
              <stop offset="100%" stopColor={cluster.color} stopOpacity="0.12" />
            </linearGradient>
          ))}
          {clusters.map((cluster) => (
            <filter key={`glow-${cluster.id}`} id={`galaxy-glow-${cluster.id}`} x="-40%" y="-40%" width="180%" height="180%">
              <feGaussianBlur stdDeviation="6" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          ))}
        </defs>
        {zones.map(({ cluster, path, center }) => (
          <g key={cluster.id}>
            <path
              d={path}
              className="galaxy-cluster-zone pointer-events-auto"
              filter={`url(#galaxy-glow-${cluster.id})`}
              style={
                {
                  "--cluster-color": cluster.color,
                  stroke: `url(#galaxy-grad-${cluster.id})`,
                } as React.CSSProperties
              }
              data-active={activeCluster === cluster.id}
              onMouseEnter={() => onHover(cluster.id)}
              onMouseLeave={() => onHover(null)}
            />
            <text
              x={center.x}
              y={center.y - 8}
              textAnchor="middle"
              className="galaxy-cluster-label"
              style={{ "--cluster-color": cluster.color } as React.CSSProperties}
            >
              {cluster.label}
            </text>
          </g>
        ))}
      </svg>
    </ViewportPortal>
  );
}
