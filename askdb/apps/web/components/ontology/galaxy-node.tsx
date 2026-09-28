"use client";

import type { OntologyNode } from "@nql/shared-types";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { Box, CalendarDays, TrendingUp, Zap } from "lucide-react";
import * as React from "react";

import { conceptCategory, type ConceptCategory } from "@/lib/ontology/kind-filter";

export type GalaxyNodeData = OntologyNode & {
  diameter: number;
  boxWidth: number;
  dimmed: boolean;
  selectedConcept: boolean;
  neighbor: boolean;
  displayLabel?: string;
};

export type GalaxyFlowNode = Node<GalaxyNodeData, "galaxy">;

const ICONS: Record<ConceptCategory, React.ComponentType<{ className?: string }>> = {
  entities: Box,
  events: Zap,
  kpis: TrendingUp,
  breakdowns: CalendarDays,
};

const HANDLE_STYLE: React.CSSProperties = {
  opacity: 0,
  width: 1,
  height: 1,
  minWidth: 0,
  minHeight: 0,
  border: 0,
  pointerEvents: "none",
};

function GalaxyNodeView({ data }: NodeProps<GalaxyFlowNode>) {
  const Icon = ICONS[conceptCategory(data)];
  const handleStyle = { ...HANDLE_STYLE, left: data.boxWidth / 2, top: data.diameter / 2 };
  return (
    <div
      className="galaxy-node-shell"
      data-dimmed={data.dimmed}
      data-selected={data.selectedConcept}
      data-neighbor={data.neighbor}
      style={{ width: data.boxWidth, "--node-color": data.clusterColor } as React.CSSProperties}
      title={data.synonyms.length ? `${data.label} — also known as ${data.synonyms.join(", ")}` : data.label}
    >
      <Handle type="target" position={Position.Top} style={handleStyle} isConnectable={false} />
      <Handle type="source" position={Position.Bottom} style={handleStyle} isConnectable={false} />
      <div className="galaxy-node" style={{ width: data.diameter, height: data.diameter }}>
        <Icon className="galaxy-node__icon" />
      </div>
      <span className="galaxy-node__caption">{data.displayLabel ?? data.label}</span>
    </div>
  );
}

export const GalaxyNode = React.memo(GalaxyNodeView);
