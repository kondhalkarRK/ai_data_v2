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
  visualKind: EdgeVisualKind;
  label: string;
  dimmed: boolean;
  emphasized: boolean;
  curvature: number;
  labelT: number;
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

  const visual = EDGE_STYLES[data.visualKind];
  const curve = curveBetween(from.center, to.center, from.radius, to.radius, data.curvature);
  const label = pointOnCurve(curve, data.labelT);
  const opacity = data.dimmed ? 0.1 : data.emphasized ? 1 : 0.7;

  return (
    <>
      <BaseEdge
        id={id}
        path={curve.path}
        markerEnd={markerEnd}
        className={cn(
          "galaxy-edge-path",
          data.motionEnabled && data.emphasized && !data.dimmed && "galaxy-edge-path--animated",
        )}
        style={{
          stroke: visual.color,
          strokeWidth: data.emphasized ? 2.6 : 1.6,
          opacity,
        }}
      />
      {data.label ? (
        <EdgeLabelRenderer>
          <div
            className="galaxy-edge-label nodrag nopan"
            data-emphasized={data.emphasized}
            data-dimmed={data.dimmed}
            style={
              {
                transform: `translate(-50%, -50%) translate(${label.x}px, ${label.y}px)`,
                "--edge-color": visual.color,
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
