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
  { id: "all", label: "All concepts", hint: "Show every business concept on the graph." },
  { id: "measure", label: "Outcomes", hint: "KPIs such as Revenue, Premium, or Loss ratio." },
  { id: "dimension", label: "Attributes", hint: "Ways to describe a concept — region, product, date." },
  { id: "fact", label: "Events", hint: "Business events such as a sale or a claim." },
  { id: "entity", label: "Actors", hint: "People and organizations — Dealer, Customer, Vehicle." },
  {
    id: "relationship",
    label: "Connected",
    hint: "Keep only concepts that share a relationship.",
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
