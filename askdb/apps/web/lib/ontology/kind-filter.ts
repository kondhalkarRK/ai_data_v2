import type { OntologyNode } from "@nql/shared-types";

export type OntologyKindFilter =
  | "all"
  | "measure"
  | "dimension"
  | "fact"
  | "entity"
  | "relationship";

export const ONTOLOGY_KIND_FILTERS: { id: OntologyKindFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "measure", label: "Measures" },
  { id: "dimension", label: "Dimensions" },
  { id: "fact", label: "Facts" },
  { id: "entity", label: "Entities" },
  { id: "relationship", label: "Relationships" },
];

export function isFactNode(node: Pick<OntologyNode, "kind" | "tableType" | "id">): boolean {
  return (
    node.tableType === "fact" ||
    (node.kind === "table" && node.id.toLowerCase().includes("fact"))
  );
}

/** Whether a node should stay emphasized for the active kind filter. */
export function nodeMatchesKindFilter(
  node: Pick<OntologyNode, "kind" | "tableType" | "id" | "degree">,
  filter: OntologyKindFilter,
): boolean {
  switch (filter) {
    case "all":
      return true;
    case "measure":
      return node.kind === "measure";
    case "dimension":
      return node.kind === "dimension";
    case "fact":
      return isFactNode(node);
    case "entity":
      return node.kind === "entity";
    case "relationship":
      // Keep connected nodes visible so relationship structure stays readable.
      return (node.degree ?? 0) > 0;
    default:
      return true;
  }
}
