"use client";

import type { OntologyNode } from "@nql/shared-types";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import {
  Box,
  CalendarDays,
  Database,
  Tag,
  Target,
  TrendingUp,
  Users,
  Zap,
} from "lucide-react";
import * as React from "react";

/** orb: knowledge graph · hub: relationship network · concept: simple relationship view. */
export type NodeVariant = "orb" | "hub" | "concept";

export type GalaxyNodeData = OntologyNode & {
  variant: NodeVariant;
  /** Category id from the active view (knowledge role or business category). */
  category: string;
  color: string;
  diameter: number;
  boxWidth: number;
  dimmed: boolean;
  selectedConcept: boolean;
  /** Steps from the selected concept, when one is selected. */
  hop: 1 | 2 | null;
  rank?: number;
  displayLabel?: string;
};

export type GalaxyFlowNode = Node<GalaxyNodeData, "galaxy">;

const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  entities: Box,
  events: Zap,
  kpis: TrendingUp,
  breakdowns: CalendarDays,
  actor: Users,
  event: Zap,
  entity: Database,
  attribute: Tag,
  outcome: Target,
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
  const Icon = ICONS[data.category] ?? Box;
  const handleStyle = { ...HANDLE_STYLE, left: data.boxWidth / 2, top: data.diameter / 2 };
  return (
    <div
      className="galaxy-node-shell"
      data-variant={data.variant}
      data-dimmed={data.dimmed}
      data-selected={data.selectedConcept}
      data-hop={data.hop ?? undefined}
      style={{ width: data.boxWidth, "--node-color": data.color } as React.CSSProperties}
      title={data.synonyms.length ? `${data.label} — also known as ${data.synonyms.join(", ")}` : data.label}
    >
      <Handle type="target" position={Position.Top} style={handleStyle} isConnectable={false} />
      <Handle type="source" position={Position.Bottom} style={handleStyle} isConnectable={false} />
      <div className="galaxy-node" style={{ width: data.diameter, height: data.diameter }}>
        {data.variant === "hub" ? (
          data.rank && data.rank <= 5 ? <span className="galaxy-node__rank">#{data.rank}</span> : null
        ) : (
          <Icon className="galaxy-node__icon" />
        )}
      </div>
      <span className="galaxy-node__caption">{data.displayLabel ?? data.label}</span>
    </div>
  );
}

export const GalaxyNode = React.memo(GalaxyNodeView);
