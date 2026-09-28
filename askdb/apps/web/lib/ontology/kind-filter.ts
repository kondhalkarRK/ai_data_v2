import type { OntologyNode } from "@nql/shared-types";

/** Business categories shown on the graph. Each concept belongs to exactly one. */
export type ConceptCategory = "entities" | "events" | "kpis" | "breakdowns";

export type OntologyKindFilter = "all" | ConceptCategory;

export const CONCEPT_CATEGORIES: ReadonlyArray<{
  id: ConceptCategory;
  cluster: string;
  label: string;
  color: string;
  hint: string;
}> = [
  {
    id: "entities",
    cluster: "Actors",
    label: "Business Entities",
    color: "#059669",
    hint: "The things the business deals with — Vehicle, Dealer, Customer, Region, Policy.",
  },
  {
    id: "events",
    cluster: "Events",
    label: "Business Events",
    color: "#2563eb",
    hint: "Things that happen and get recorded — a Sale, a Claim, a Premium payment.",
  },
  {
    id: "kpis",
    cluster: "Outcomes",
    label: "KPIs",
    color: "#db2777",
    hint: "The numbers leaders track — Revenue, Units Sold, Loss Ratio.",
  },
  {
    id: "breakdowns",
    cluster: "Attributes",
    label: "Time & Breakdowns",
    color: "#ca8a04",
    hint: "Ways to slice a KPI — by date, month, or year.",
  },
];

const CATEGORY_BY_CLUSTER = new Map(CONCEPT_CATEGORIES.map((item) => [item.cluster, item]));

export function categoryMeta(category: ConceptCategory) {
  return CONCEPT_CATEGORIES.find((item) => item.id === category)!;
}

/** Business label for a cluster id coming from the API (Actors, Events, …). */
export function categoryLabelForCluster(cluster: string): string {
  return CATEGORY_BY_CLUSTER.get(cluster)?.label ?? cluster;
}

export function isFactNode(node: Pick<OntologyNode, "kind" | "tableType" | "id">): boolean {
  return (
    node.tableType === "fact" ||
    (node.kind === "table" && node.id.toLowerCase().includes("fact"))
  );
}

export function conceptCategory(
  node: Pick<OntologyNode, "kind" | "tableType" | "id">,
): ConceptCategory {
  if (isFactNode(node)) return "events";
  if (node.kind === "measure") return "kpis";
  if (node.kind === "dimension") return "breakdowns";
  return "entities";
}

export function nodeMatchesKindFilter(
  node: Pick<OntologyNode, "kind" | "tableType" | "id">,
  filter: OntologyKindFilter,
): boolean {
  return filter === "all" || conceptCategory(node) === filter;
}

/** A node stays visible when it matches any selected category. "All" clears the filter. */
export function nodeMatchesKindFilters(
  node: Pick<OntologyNode, "kind" | "tableType" | "id">,
  filters: readonly OntologyKindFilter[],
): boolean {
  if (filters.length === 0 || filters.includes("all")) return true;
  return filters.some((filter) => nodeMatchesKindFilter(node, filter));
}
