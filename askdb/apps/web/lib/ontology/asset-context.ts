import type { OntologyEdge, OntologyNode, OntologySnapshot } from "@nql/shared-types";

export type ContextOverlay = "business" | "technical" | "governance";

export type TrustBadge = "certified" | "trusted" | "popular" | "review";

export interface AssetContext {
  owner: string;
  qualityScore: number;
  popularityScore: number;
  lastUpdated: string;
  badges: TrustBadge[];
  sampleQueries: string[];
  relatedMetrics: OntologyNode[];
  relatedGlossary: string[];
  connectedTables: string[];
}

function hashScore(id: string, min: number, max: number): number {
  let n = 0;
  for (let i = 0; i < id.length; i += 1) n = (n * 31 + id.charCodeAt(i)) % 997;
  return min + (n % (max - min + 1));
}

export function deriveAssetContext(node: OntologyNode, snapshot: OntologySnapshot): AssetContext {
  const qualityScore = Math.min(98, 68 + node.degree * 4 + (node.synonyms.length ? 4 : 0));
  const popularityScore = Math.min(99, 40 + node.degree * 8);
  const badges: TrustBadge[] = [];
  if (node.kind === "measure" || node.degree >= 5) badges.push("certified");
  else if (qualityScore >= 80) badges.push("trusted");
  if (node.degree >= 4) badges.push("popular");
  if (node.kind === "table" && node.degree < 2) badges.push("review");

  const neighborIds = new Set<string>();
  for (const edge of snapshot.edges) {
    if (edge.source === node.id) neighborIds.add(edge.target);
    if (edge.target === node.id) neighborIds.add(edge.source);
  }
  const neighbors = snapshot.nodes.filter((item) => neighborIds.has(item.id));
  const relatedMetrics = neighbors.filter((item) => item.kind === "measure").slice(0, 6);
  const relatedGlossary = [...node.synonyms, ...neighbors.flatMap((item) => item.synonyms)].slice(0, 8);
  const connectedTables = [
    ...node.tables,
    ...neighbors.filter((item) => item.kind === "table").map((item) => item.physicalName || item.label),
  ].filter(Boolean);

  const sampleQueries = sampleQueriesFor(node);
  const ownerRole = node.kind === "measure" ? "KPI Owner" : node.kind === "table" ? "Data Steward" : "Domain Owner";

  return {
    owner: `${node.domain} ${ownerRole}`,
    qualityScore,
    popularityScore,
    lastUpdated: snapshot.metadata.compiledAt,
    badges: [...new Set(badges)],
    sampleQueries,
    relatedMetrics,
    relatedGlossary: [...new Set(relatedGlossary)].slice(0, 8),
    connectedTables: [...new Set(connectedTables)].slice(0, 8),
  };
}

function sampleQueriesFor(node: OntologyNode): string[] {
  const name = node.label;
  if (node.kind === "measure") {
    return [`Trend of ${name} by month`, `Top 10 dealers by ${name}`, `${name} vs last year`];
  }
  if (node.kind === "table") {
    return [`Show volume from ${name}`, `Break ${name} down by region`];
  }
  return [`${name} by month`, `Share of ${name}`];
}

export function storyVerb(edge: OntologyEdge): string {
  if (edge.kind === "maps_to") return "Defined as";
  if (edge.kind === "reference") return "Joined through";
  if (edge.kind === "dependency") return "Depends on";
  if (edge.fromColumn || edge.toColumn) return "Joined through";
  return "Related to";
}

export function storyLabel(edge: OntologyEdge, overlay: ContextOverlay): string {
  if (overlay === "technical" && (edge.fromColumn || edge.toColumn)) {
    return [edge.fromColumn, edge.toColumn].filter(Boolean).join(" → ");
  }
  if (overlay === "governance") return edge.kind.replace("_", " ");
  return edge.label || storyVerb(edge);
}

export function displayName(node: OntologyNode, overlay: ContextOverlay): string {
  if (overlay === "technical") return node.physicalName || node.id;
  return node.label;
}

export function snapshotTrustRate(snapshot: OntologySnapshot): number {
  if (!snapshot.nodes.length) return 0;
  const trusted = snapshot.nodes.filter((node) => node.kind === "measure" || node.degree >= 3).length;
  return Math.round((trusted / snapshot.nodes.length) * 100);
}

export const JOURNEYS: Array<{ id: string; label: string; seeds: string[] }> = [
  { id: "revenue", label: "Revenue journey", seeds: ["revenue", "sales", "dealer", "region"] },
  { id: "claims", label: "Claims journey", seeds: ["claim", "premium", "policy", "customer"] },
  { id: "vehicle", label: "Vehicle journey", seeds: ["vehicle", "car", "make", "model"] },
];

export function journeyNodeIds(snapshot: OntologySnapshot, seeds: string[]): string[] {
  const ids: string[] = [];
  for (const seed of seeds) {
    const needle = seed.toLowerCase();
    const match = snapshot.nodes.find(
      (node) =>
        node.id.toLowerCase().includes(needle) ||
        node.label.toLowerCase().includes(needle) ||
        node.synonyms.some((item) => item.toLowerCase().includes(needle)),
    );
    if (match && !ids.includes(match.id)) ids.push(match.id);
  }
  return ids;
}

export function matchesDiscoveryQuery(node: OntologyNode, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return false;
  if (node.label.toLowerCase().includes(q) || node.id.toLowerCase().includes(q)) return true;
  if (node.domain.toLowerCase().includes(q) || node.kind.toLowerCase().includes(q)) return true;
  if (node.physicalName?.toLowerCase().includes(q)) return true;
  if (node.synonyms.some((item) => item.toLowerCase().includes(q))) return true;
  return node.columns.some(
    (col) => col.name.toLowerCase().includes(q) || col.displayName.toLowerCase().includes(q),
  );
}
