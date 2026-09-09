import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { motion } from "framer-motion";
import type { OntologyNodeData } from "@/lib/types";

function OntologyNodeComponent({
  data,
  selected,
}: NodeProps & { data: OntologyNodeData }) {
  const color = data.clusterColor || "#64748b";
  const radius = Math.max(18, Math.min(52, 16 + data.degree * 3 + (data.kind === "domain" ? 14 : 0)));

  return (
    <div className="onto-node-wrap">
      <Handle type="target" position={Position.Top} className="onto-handle" />
      <motion.button
        type="button"
        className={`onto-circle${selected ? " is-selected" : ""}`}
        style={
          {
            "--accent": color,
            width: radius * 2,
            height: radius * 2,
          } as React.CSSProperties
        }
        initial={{ scale: 0.7, opacity: 0 }}
        animate={{
          scale: selected ? 1.12 : 1,
          opacity: data.dimmed ? 0.22 : 1,
          boxShadow: selected
            ? `0 0 0 3px #fff, 0 0 0 6px ${color}, 0 0 28px ${color}99`
            : `0 0 0 2px #fff, 0 6px 16px rgba(15,23,42,.12)`,
        }}
        whileHover={{ scale: selected ? 1.14 : 1.08 }}
        transition={{ type: "spring", stiffness: 380, damping: 24 }}
        title={data.label}
      >
        <span className="onto-circle__fill" />
      </motion.button>
      <div
        className={`onto-label${selected ? " is-selected" : ""}`}
        style={{ opacity: data.dimmed ? 0.25 : 1 }}
      >
        {data.label}
      </div>
      <Handle type="source" position={Position.Bottom} className="onto-handle" />
    </div>
  );
}

export const OntologyNode = memo(OntologyNodeComponent);
