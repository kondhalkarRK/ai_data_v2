"use client";

import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";
import * as React from "react";

import { cn } from "@/lib/utils";

export type EdgeVisualKind =
  | "primary_key"
  | "foreign_key"
  | "semantic"
  | "ai_inferred"
  | "lineage";

export const EDGE_STYLES: Record<
  EdgeVisualKind,
  { color: string; width: number; animated: boolean; label: string }
> = {
  primary_key: { color: "#38bdf8", width: 2.4, animated: true, label: "PK" },
  foreign_key: { color: "#34d399", width: 2, animated: true, label: "FK" },
  semantic: { color: "#a78bfa", width: 1.6, animated: false, label: "SEM" },
  ai_inferred: { color: "#fbbf24", width: 1.8, animated: true, label: "AI" },
  lineage: { color: "#fb7185", width: 2.2, animated: true, label: "LIN" },
};

export type GalaxyEdgeData = {
  visualKind: EdgeVisualKind;
  label: string;
  dimmed: boolean;
  emphasized: boolean;
};

export type GalaxyFlowEdge = Edge<GalaxyEdgeData, "galaxy">;

export function GalaxyEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps<GalaxyFlowEdge>) {
  const visual = EDGE_STYLES[data?.visualKind ?? "semantic"];
  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    curvature: 0.28,
  });

  const strokeWidth = data?.emphasized ? visual.width + 1.2 : visual.width;
  const opacity = data?.dimmed ? 0.08 : data?.emphasized ? 1 : 0.72;

  const animated = !data?.dimmed && (visual.animated || Boolean(data?.emphasized));

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        className={cn(
          "galaxy-edge-path",
          animated && "galaxy-edge-path--animated",
          data?.dimmed && "galaxy-edge-path--dimmed",
        )}
        style={
          {
            stroke: visual.color,
            strokeWidth,
            opacity,
            "--edge-color": visual.color,
          } as React.CSSProperties
        }
      />
      {!data?.dimmed && data?.emphasized ? (
        <EdgeLabelRenderer>
          <div
            className="nodrag nopan pointer-events-none absolute rounded-full border border-white/10 px-1.5 py-0.5 text-[9px] font-semibold tracking-[0.12em] text-white/90 shadow-lg backdrop-blur"
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              background: `color-mix(in oklab, ${visual.color} 55%, #0b1220)`,
            }}
          >
            {data.label || visual.label}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}
