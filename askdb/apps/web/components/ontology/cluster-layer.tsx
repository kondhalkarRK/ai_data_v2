"use client";

import type { OntologyCluster } from "@nql/shared-types";
import { ViewportPortal } from "@xyflow/react";
import * as React from "react";

import {
  centroid,
  convexHull,
  expandHull,
  hullToPath,
  smoothHullPath,
  type Point,
} from "@/lib/ontology/hull";
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

/** Rounded community outline: circle samples around each concept and its caption, smoothed. */
export function organicZones(clusters: OntologyCluster[], nodes: PositionedNode[]): ClusterZone[] {
  return clusters
    .map((cluster) => {
      const members = nodes.filter((node) => node.cluster === cluster.id);
      if (!members.length) return null;
      const points: Point[] = [];
      for (const node of members) {
        const reach = Math.max(node.radius + 26, node.captionWidth / 2 + 16);
        for (let step = 0; step < 12; step += 1) {
          const angle = (step / 12) * Math.PI * 2;
          points.push({ x: node.x + Math.cos(angle) * reach, y: node.y + Math.sin(angle) * reach });
        }
        points.push({ x: node.x, y: node.y + node.radius + CAPTION_HEIGHT + 22 });
      }
      const hull = expandHull(convexHull(points), 22);
      const top = Math.min(...hull.map((point) => point.y));
      return { cluster, path: smoothHullPath(hull), labelX: centroid(hull).x, labelY: top + 26 };
    })
    .filter((zone): zone is ClusterZone => zone !== null);
}

/** Business-domain communities for the Ontology Map. The focused domain stays vivid. */
export function DomainLayer({
  clusters,
  nodes,
  focusId,
}: {
  clusters: OntologyCluster[];
  nodes: PositionedNode[];
  focusId: string | null;
}) {
  const zones = React.useMemo(() => organicZones(clusters, nodes), [clusters, nodes]);
  return (
    <ViewportPortal>
      <svg
        className="pointer-events-none"
        style={{ position: "absolute", left: 0, top: 0, width: 1, height: 1, overflow: "visible" }}
        aria-hidden="true"
      >
        {zones.map(({ cluster, path, labelX, labelY }) => (
          <g
            key={cluster.id}
            className="ontology-domain"
            data-dimmed={focusId !== null && focusId !== cluster.id}
            style={{ "--cluster-color": cluster.color } as React.CSSProperties}
          >
            <path d={path} className="ontology-domain__zone" />
            <text x={labelX} y={labelY} textAnchor="middle" className="ontology-domain__label">
              {cluster.label}
            </text>
          </g>
        ))}
      </svg>
    </ViewportPortal>
  );
}

/** Screen box of a zone title, so edge labels can be kept off it. */
export function clusterLabelBox(zone: ClusterZone) {
  const width = zone.cluster.label.length * 9.5 + 20;
  return { x: zone.labelX - width / 2, y: zone.labelY - 16, width, height: 22 };
}

/** Concentric guide circles behind the influence layout. */
export function RingLayer({ radii }: { radii: number[] }) {
  return (
    <ViewportPortal>
      <svg
        className="pointer-events-none"
        style={{ position: "absolute", left: 0, top: 0, width: 1, height: 1, overflow: "visible" }}
        aria-hidden="true"
      >
        {radii.map((radius, index) => (
          <g key={radius}>
            <circle cx={0} cy={0} r={radius} className="galaxy-ring" />
            <text x={0} y={-radius - 10} textAnchor="middle" className="galaxy-ring-label">
              {index === 0 ? "Closest to the core" : index === radii.length - 1 ? "Edge of the network" : ""}
            </text>
          </g>
        ))}
        <circle cx={0} cy={0} r={8} className="galaxy-ring-core" />
      </svg>
    </ViewportPortal>
  );
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
