"use client";

import {
  BaseEdge,
  EdgeLabelRenderer,
  useInternalNode,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";
import * as React from "react";

import type { GalaxyFlowNode } from "@/components/ontology/galaxy-node";
import { curveBetween, pointOnCurve } from "@/lib/ontology/edge-geometry";
import type { EdgeVisualKind } from "@/lib/ontology/layouts";
import { cn } from "@/lib/utils";

export const EDGE_STYLES: Record<EdgeVisualKind, { color: string; label: string }> = {
  relationship: { color: "#60a5fa", label: "Business relationship" },
  measure: { color: "#f472b6", label: "KPI calculated from" },
  describes: { color: "#fbbf24", label: "Breakdown of" },
};

export type GalaxyEdgeData = {
  color: string;
  label: string;
  /** Show the verb pill. Hidden labels still appear once the edge is emphasized. */
  labelVisible: boolean;
  dimmed: boolean;
  emphasized: boolean;
  /** Second-step edge around the selection: visible but quiet. */
  secondary: boolean;
  curvature: number;
  labelT: number;
  glow: boolean;
  motionEnabled: boolean;
};

export type GalaxyFlowEdge = Edge<GalaxyEdgeData, "galaxy">;

function circleOf(node: ReturnType<typeof useInternalNode<GalaxyFlowNode>>) {
  if (!node) return null;
  const { x, y } = node.internals.positionAbsolute;
  const data = node.data;
  return {
    center: { x: x + data.boxWidth / 2, y: y + data.diameter / 2 },
    radius: data.diameter / 2 + 4,
  };
}

function GalaxyEdgeView({ id, source, target, data, markerEnd }: EdgeProps<GalaxyFlowEdge>) {
  const sourceNode = useInternalNode<GalaxyFlowNode>(source);
  const targetNode = useInternalNode<GalaxyFlowNode>(target);
  const from = circleOf(sourceNode);
  const to = circleOf(targetNode);
  if (!from || !to || !data) return null;

  const curve = curveBetween(from.center, to.center, from.radius, to.radius, data.curvature);
  const label = pointOnCurve(curve, data.labelT);
  const opacity = data.dimmed ? 0.08 : data.emphasized ? 1 : data.secondary ? 0.45 : 0.62;
  const showLabel = Boolean(data.label) && !data.dimmed && (data.labelVisible || data.emphasized);

  return (
    <>
      <BaseEdge
        id={id}
        path={curve.path}
        markerEnd={markerEnd}
        className={cn(
          "galaxy-edge-path",
          data.glow && "galaxy-edge-path--glow",
          data.motionEnabled && data.emphasized && !data.dimmed && "galaxy-edge-path--animated",
        )}
        style={
          {
            stroke: data.color,
            strokeWidth: data.emphasized ? 2.6 : 1.5,
            opacity,
            "--edge-color": data.color,
          } as React.CSSProperties
        }
      />
      {showLabel ? (
        <EdgeLabelRenderer>
          <div
            className="galaxy-edge-label nodrag nopan"
            data-emphasized={data.emphasized}
            style={
              {
                transform: `translate(-50%, -50%) translate(${label.x}px, ${label.y}px)`,
                "--edge-color": data.color,
              } as React.CSSProperties
            }
          >
            {data.label}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

export const GalaxyEdge = React.memo(GalaxyEdgeView);
