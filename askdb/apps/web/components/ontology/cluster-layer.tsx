"use client";

import type { OntologyCluster } from "@nql/shared-types";
import { ViewportPortal } from "@xyflow/react";
import * as React from "react";

import { centroid, convexHull, expandHull, hullToPath, type Point } from "@/lib/ontology/hull";
import { CAPTION_HEIGHT, type PositionedNode } from "@/lib/ontology/layouts";

export type ClusterZone = {
  cluster: OntologyCluster;
  path: string;
  labelX: number;
  labelY: number;
};

export function clusterZones(clusters: OntologyCluster[], nodes: PositionedNode[]): ClusterZone[] {
  return clusters
    .map((cluster) => {
      const members = nodes.filter((node) => node.cluster === cluster.id);
      if (!members.length) return null;
      const points: Point[] = [];
      for (const node of members) {
        const half = Math.max(node.radius, node.captionWidth / 2) + 18;
        points.push(
          { x: node.x - half, y: node.y - node.radius - 18 },
          { x: node.x + half, y: node.y - node.radius - 18 },
          { x: node.x - half, y: node.y + node.radius + CAPTION_HEIGHT + 12 },
          { x: node.x + half, y: node.y + node.radius + CAPTION_HEIGHT + 12 },
        );
      }
      const hull = expandHull(convexHull(points), 20);
      const top = Math.min(...hull.map((point) => point.y));
      return { cluster, path: hullToPath(hull), labelX: centroid(hull).x, labelY: top - 10 };
    })
    .filter((zone): zone is ClusterZone => zone !== null);
}

/** Screen box of a zone title, so edge labels can be kept off it. */
export function clusterLabelBox(zone: ClusterZone) {
  const width = zone.cluster.label.length * 9.5 + 20;
  return { x: zone.labelX - width / 2, y: zone.labelY - 16, width, height: 22 };
}

/** Soft, static background zones per business category. They never react to the pointer. */
export function ClusterLayer({
  clusters,
  nodes,
}: {
  clusters: OntologyCluster[];
  nodes: PositionedNode[];
}) {
  const zones = React.useMemo(() => clusterZones(clusters, nodes), [clusters, nodes]);

  return (
    <ViewportPortal>
      <svg
        className="pointer-events-none"
        style={{ position: "absolute", left: 0, top: 0, width: 1, height: 1, overflow: "visible" }}
        aria-hidden="true"
      >
        {zones.map(({ cluster, path, labelX, labelY }) => (
          <g key={cluster.id} style={{ "--cluster-color": cluster.color } as React.CSSProperties}>
            <path d={path} className="galaxy-cluster-zone" />
            <text x={labelX} y={labelY} textAnchor="middle" className="galaxy-cluster-label">
              {cluster.label}
            </text>
          </g>
        ))}
      </svg>
    </ViewportPortal>
  );
}
