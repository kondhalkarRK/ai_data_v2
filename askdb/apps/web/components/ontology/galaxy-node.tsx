"use client";

import type { OntologyNode } from "@nql/shared-types";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { motion } from "framer-motion";
import * as React from "react";

import { cn } from "@/lib/utils";

export type GalaxyNodeData = OntologyNode & {
  radius: number;
  centrality: number;
  dimmed: boolean;
  focused: boolean;
  pulsing: boolean;
  hop: 0 | 1 | 2 | null;
  /** When false, idle float / pulse motion is suppressed. */
  motionEnabled: boolean;
  displayLabel?: string;
  certified?: boolean;
  review?: boolean;
};

export type GalaxyFlowNode = Node<GalaxyNodeData, "galaxy">;

export function GalaxyNode({ data, selected }: NodeProps<GalaxyFlowNode>) {
  const isFact =
    data.tableType === "fact" || (data.kind === "table" && data.id.includes("fact"));
  const size = Math.max(36, data.radius * 2);

  return (
    <motion.div
      className="relative"
      style={{ width: size + 24, height: size + 28 }}
      initial={false}
      animate={{
        scale: selected || data.focused ? 1.06 : 1,
        y: data.motionEnabled && data.pulsing ? [0, -3, 0] : 0,
      }}
      transition={{
        scale: { type: "spring", stiffness: 380, damping: 24 },
        y:
          data.motionEnabled && data.pulsing
            ? { duration: 2.4, repeat: Infinity, ease: "easeInOut" }
            : { duration: 0.2 },
      }}
    >
      <Handle type="target" position={Position.Left} className="!opacity-0" />
      <Handle type="source" position={Position.Right} className="!opacity-0" />
      <div
        className={cn("galaxy-node")}
        title={`${data.label}${data.domain ? ` · ${data.domain}` : ""}`}
        data-fact={isFact}
        data-focused={data.focused || selected}
        data-dimmed={data.dimmed}
        data-pulse={data.motionEnabled && data.pulsing}
        style={
          {
            "--node-color": data.clusterColor,
            width: size,
            height: size,
            marginInline: "auto",
          } as React.CSSProperties
        }
      >
        <span className="galaxy-node__label">{data.displayLabel ?? data.label}</span>
      </div>
      {data.certified ? (
        <span className="pointer-events-none absolute -left-0.5 -top-0.5 rounded-full bg-success/90 px-1 text-[8px] font-bold text-white">
          ✓
        </span>
      ) : null}
      {data.review ? (
        <span className="pointer-events-none absolute -left-0.5 -top-0.5 rounded-full bg-warning px-1 text-[8px] font-bold">
          !
        </span>
      ) : null}
      {data.hop != null && data.hop > 0 ? (
        <span className="pointer-events-none absolute -right-1 -top-1 rounded-full border border-border/60 bg-surface-raised/90 px-1.5 py-0.5 text-[9px] font-semibold tracking-wide text-muted-foreground shadow-sm backdrop-blur">
          {data.hop}h
        </span>
      ) : null}
    </motion.div>
  );
}
