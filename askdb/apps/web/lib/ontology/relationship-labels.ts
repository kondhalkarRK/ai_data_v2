import type { OntologyEdge, OntologyNode } from "@nql/shared-types";

import { conceptCategory } from "@/lib/ontology/kind-filter";

const TARGET_VERBS: Array<[RegExp, string]> = [
  [/\b(region|geography|territory|city|location)\b/, "located in"],
  [/\b(salesperson|salesman|sales rep)\b/, "closed by"],
  [/\b(dealer|agent|broker|intermediary)\b/, "sold by"],
  [/\b(customer|policyholder)\b/, "owned by"],
  [/\bpolicy\b/, "linked to"],
  [/\bproduct\b/, "for product"],
  [/\b(vehicle|car|carline|automobile)\b/, "involves"],
  [/\b(colou?r|paint)\b/, "in colour"],
  [/\btarget\b/, "planned in"],
];

/**
 * Read-aloud verb for an edge, so "Sale → sold by → Dealer" replaces
 * warehouse labels such as "sales_to_dealer" or "maps to".
 */
export function relationshipVerb(
  edge: Pick<OntologyEdge, "kind" | "label">,
  source: Pick<OntologyNode, "kind" | "tableType" | "id" | "label">,
  target: Pick<OntologyNode, "kind" | "tableType" | "id" | "label">,
): string {
  const sourceCategory = conceptCategory(source);
  if (sourceCategory === "kpis") return "measured from";
  if (sourceCategory === "breakdowns") return "describes";
  if (edge.kind === "maps_to" || edge.kind === "dependency") return "part of";
  const targetLabel = target.label.toLowerCase();
  for (const [pattern, verb] of TARGET_VERBS) {
    if (pattern.test(targetLabel)) return verb;
  }
  return "connected to";
}
