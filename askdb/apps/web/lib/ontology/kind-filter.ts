import type { OntologyNode } from "@nql/shared-types";

export type OntologyKindFilter =
  | "all"
  | "measure"
  | "dimension"
  | "fact"
  | "entity"
  | "relationship";

export const ONTOLOGY_KIND_FILTERS: {
  id: OntologyKindFilter;
  label: string;
  hint: string;
}[] = [
  { id: "all", label: "All assets", hint: "Show every asset on the map." },
  { id: "measure", label: "Measures", hint: "KPIs and calculations, such as Revenue or Premium." },
  { id: "dimension", label: "Dimensions", hint: "Ways to slice a number — region, date, product." },
  { id: "fact", label: "Facts", hint: "Transaction tables that feed the metrics." },
  { id: "entity", label: "Entities", hint: "Business objects such as Dealer, Customer, or Vehicle." },
  {
    id: "relationship",
    label: "Connected",
    hint: "Hide isolated assets and keep only nodes that share a relationship.",
  },
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
