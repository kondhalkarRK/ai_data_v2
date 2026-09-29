import type {
  GlossaryTerm,
  Industry,
  OntologyEdge,
  OntologyNode,
  OntologySnapshot,
} from "@nql/shared-types";
import {
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type SimulationNodeDatum,
} from "d3-force";

import { degreeCentrality, pageRank } from "@/lib/ontology/graph-metrics";
import {
  CAPTION_HEIGHT,
  captionWidth,
  resolveOverlaps,
  type PositionedNode,
} from "@/lib/ontology/layouts";
import {
  mergeOntologyConcepts,
  normalizeConceptKey,
  withoutDomainNodes,
} from "@/lib/ontology/merge-concepts";

/** force: domains as communities · centrality: core concepts pulled to the middle · hierarchy: domain trees. */
export type OntologyMapStyle = "force" | "centrality" | "hierarchy";

export type BusinessDomain = {
  id: string;
  label: string;
  color: string;
  hint: string;
  /** Concept names that belong here, compared after normalisation. */
  concepts: string[];
  /** Glossary categories that fall into this domain when the name is not listed. */
  categories: string[];
};

type IndustryDomains = {
  domains: BusinessDomain[];
  /** Business formulas the glossary names but does not map to a column. */
  derived: Record<string, string[]>;
};

const OTHER_DOMAIN: BusinessDomain = {
  id: "other",
  label: "Other",
  color: "#94a3b8",
  hint: "Concepts not yet assigned to a business domain.",
  concepts: [],
  categories: [],
};

const DOMAINS: Record<Industry, IndustryDomains> = {
  automotive: {
    domains: [
      {
        id: "vehicle",
        label: "Vehicle",
        color: "#6366f1",
        hint: "What is sold: brands, models, body styles, fuel types and colours.",
        concepts: [
          "Vehicle",
          "Car Type",
          "Sedan",
          "SUV",
          "Hatchback",
          "MUV",
          "Coupe",
          "Electric Vehicle",
          "Fuel Type",
          "Petrol",
          "Diesel",
          "Hybrid",
          "Brand",
          "Colour",
          "Colour Variant",
        ],
        categories: ["Product", "Product Filter", "Product Attribute"],
      },
      {
        id: "sales",
        label: "Sales",
        color: "#10b981",
        hint: "What the business measures: sales, revenue, orders, targets and growth.",
        concepts: [
          "Sales Transaction",
          "Revenue",
          "Units Sold",
          "Orders",
          "Average Selling Price",
          "Market Share",
          "Growth",
          "Sales Target",
          "Target Units",
          "Target Revenue",
          "Date",
        ],
        categories: [
          "Financial",
          "Sales Volume",
          "Sales Activity",
          "Pricing",
          "Planning",
          "Market",
          "Time",
        ],
      },
      {
        id: "dealer",
        label: "Dealer",
        color: "#f59e0b",
        hint: "Who sells: dealers, showrooms and the sales team.",
        concepts: ["Dealer", "Salesperson", "Active Salespeople"],
        categories: ["Network", "People"],
      },
      {
        id: "geography",
        label: "Geography",
        color: "#06b6d4",
        hint: "Where it happens: regions, states and cities.",
        concepts: ["Region", "Location"],
        categories: ["Geography"],
      },
    ],
    derived: {
      "Market Share": ["Units Sold", "Revenue", "Brand"],
      Growth: ["Revenue", "Units Sold", "Date"],
    },
  },
  insurance: {
    domains: [
      {
        id: "policy",
        label: "Policy & Customer",
        color: "#6366f1",
        hint: "What is sold and to whom: policies, products, coverage and retention.",
        concepts: [
          "Policy",
          "Product",
          "Line of Business",
          "Coverage Tier",
          "Policy Status",
          "Renewal Rate",
        ],
        categories: ["Product", "Product Filter", "Policy Filter", "Customer"],
      },
      {
        id: "premium",
        label: "Premium",
        color: "#10b981",
        hint: "Money in: written and earned premium over time.",
        concepts: ["Premium Exposure", "Gross Written Premium", "Earned Premium", "Accounting Month"],
        categories: ["Financial"],
      },
      {
        id: "claims",
        label: "Claims & Risk",
        color: "#ef4444",
        hint: "Money out: claims, payouts, severity and loss ratio.",
        concepts: [
          "Claim",
          "Claims Incurred",
          "Claims Paid",
          "Claim Count",
          "Claim Status",
          "Average Claim Severity",
          "Approval Rate",
          "Loss Ratio",
          "Claim Frequency",
          "Reported Date",
        ],
        categories: ["Claims", "Claims Filter", "Risk", "Operations"],
      },
      {
        id: "distribution",
        label: "Distribution",
        color: "#f59e0b",
        hint: "Who sells: agents, brokers and channels.",
        concepts: ["Agent", "Distribution Channel"],
        categories: ["People", "Distribution Filter"],
      },
      {
        id: "geography",
        label: "Geography",
        color: "#06b6d4",
        hint: "Where it happens: regions and territories.",
        concepts: ["Region"],
        categories: ["Geography", "Time"],
      },
    ],
    derived: {},
  },
};

export type OntologyMap = {
  graph: OntologySnapshot;
  domains: BusinessDomain[];
  domainOf: Map<string, string>;
  /** Edge ids whose two ends live in different domains. */
  crossEdges: Set<string>;
  /** Domain pairs and how many relationships connect them, strongest first. */
  bridges: Array<{ from: string; to: string; count: number }>;
};

type ColumnRef = { table: string; column: string };

const COLUMN_REF = /([a-z_]\w*)\.([a-z_]\w*)\s*(?:=|$)/i;
const TAXONOMY_LABEL = "is a kind of";

function columnRef(term: GlossaryTerm): ColumnRef | null {
  const match = COLUMN_REF.exec(term.mapsToAttribute ?? "") ?? COLUMN_REF.exec(term.sqlExpression ?? "");
  return match ? { table: match[1]!, column: match[2]! } : null;
}

function isValueTerm(term: GlossaryTerm): boolean {
  return /=\s*'/.test(term.sqlExpression ?? "");
}

const TABLE_KIND_RANK: Partial<Record<OntologyNode["kind"], number>> = {
  entity: 3,
  table: 2,
  dimension: 1,
};

export function domainsFor(industry: Industry): IndustryDomains {
  return DOMAINS[industry] ?? { domains: [], derived: {} };
}

/**
 * Business concepts (physical tables folded into the concept they record) enriched with
 * glossary terms, each placed in a business domain. Glossary terms without any mapping and no
 * known formula are left out: they describe data the model does not have.
 */
export function buildOntologyMap(
  snapshot: OntologySnapshot,
  glossary: Record<string, GlossaryTerm> = {},
): OntologyMap {
  const config = domainsFor(snapshot.metadata.industry);
  const base = mergeOntologyConcepts(withoutDomainNodes(snapshot));
  const nodes = base.nodes.map((node) => ({ ...node, synonyms: [...node.synonyms] }));
  const edges: OntologyEdge[] = [...base.edges];
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const byLabel = new Map(nodes.map((node) => [normalizeConceptKey(node.label), node.id]));
  const categoryOf = new Map<string, string>();

  const bySynonym = (name: string) => {
    const key = normalizeConceptKey(name);
    return (
      byLabel.get(key) ??
      nodes.find((node) => node.synonyms.some((alias) => normalizeConceptKey(alias) === key))?.id
    );
  };

  const termNode = new Map<string, string>();
  for (const [name, term] of Object.entries(glossary)) {
    const label = term.displayLabel || name;
    const value = isValueTerm(term);
    const existing =
      byLabel.get(normalizeConceptKey(label)) ??
      (term.mapsToMeasure && byId.has(`measure:${term.mapsToMeasure}`)
        ? `measure:${term.mapsToMeasure}`
        : undefined) ??
      (!value && term.mapsToDimension ? bySynonym(term.mapsToDimension) : undefined);
    if (existing) {
      const node = byId.get(existing)!;
      if (!node.description) node.description = term.definition;
      const known = new Set([node.label, ...node.synonyms].map(normalizeConceptKey));
      for (const alias of term.synonyms) {
        if (!known.has(normalizeConceptKey(alias))) node.synonyms.push(alias);
      }
      termNode.set(name, existing);
      categoryOf.set(existing, term.category);
      continue;
    }
    const mapped =
      term.mapsToMeasure || term.mapsToDimension || term.mapsToAttribute || term.sqlExpression;
    if (!mapped && !config.derived[name]) continue;
    const ref = columnRef(term);
    const id = `term:${name}`;
    const node: OntologyNode = {
      id,
      label,
      kind: term.mapsToMeasure || config.derived[name] ? "measure" : "dimension",
      domain: snapshot.metadata.industry,
      description: term.definition,
      synonyms: [...term.synonyms],
      tables: ref ? [ref.table] : [],
      columns: [],
      relationships: [],
      lineage: [],
      degree: 0,
      cluster: OTHER_DOMAIN.id,
      clusterColor: OTHER_DOMAIN.color,
    };
    nodes.push(node);
    byId.set(id, node);
    byLabel.set(normalizeConceptKey(label), id);
    termNode.set(name, id);
    categoryOf.set(id, term.category);
  }

  const pairs = new Set(edges.map((edge) => [edge.source, edge.target].sort().join("|")));
  const link = (source: string | undefined, target: string | undefined, label: string) => {
    if (!source || !target || source === target) return;
    const pair = [source, target].sort().join("|");
    if (pairs.has(pair)) return;
    pairs.add(pair);
    edges.push({ id: `map:${source}->${target}`, source, target, kind: "relationship", label });
  };

  const tableConcept = (table: string) =>
    nodes
      .filter((node) => node.kind !== "measure" && TABLE_KIND_RANK[node.kind] && node.tables.includes(table))
      .sort(
        (a, b) =>
          (TABLE_KIND_RANK[b.kind] ?? 0) - (TABLE_KIND_RANK[a.kind] ?? 0) || b.degree - a.degree,
      )[0]?.id;

  const attributeTerm = (ref: ColumnRef) => {
    for (const [name, term] of Object.entries(glossary)) {
      if (isValueTerm(term)) continue;
      const other = columnRef(term);
      if (other && other.table === ref.table && other.column === ref.column) return termNode.get(name);
    }
    return undefined;
  };

  for (const [name, term] of Object.entries(glossary)) {
    const id = termNode.get(name);
    if (!id?.startsWith("term:")) continue;
    const ref = columnRef(term);
    if (isValueTerm(term) && ref) {
      link(id, attributeTerm(ref) ?? tableConcept(ref.table), TAXONOMY_LABEL);
    } else if (ref) {
      link(id, tableConcept(ref.table), "describes");
    }
    if (term.mapsToDimension) link(id, bySynonym(term.mapsToDimension), TAXONOMY_LABEL);
    if (term.mapsToMeasure) link(id, `measure:${term.mapsToMeasure}`, "measures");
    for (const source of config.derived[name] ?? []) {
      link(id, termNode.get(source) ?? byLabel.get(normalizeConceptKey(source)), "calculated from");
    }
  }
  for (const [name, term] of Object.entries(glossary)) {
    for (const related of term.relatedTerms) {
      link(termNode.get(name), termNode.get(related) ?? byLabel.get(normalizeConceptKey(related)), "related to");
    }
  }

  const domainByConcept = new Map<string, BusinessDomain>();
  const domainByCategory = new Map<string, BusinessDomain>();
  for (const domain of config.domains) {
    for (const concept of domain.concepts) domainByConcept.set(normalizeConceptKey(concept), domain);
    for (const category of domain.categories) domainByCategory.set(category, domain);
  }
  const metricsDomain = domainByCategory.get("Financial");

  const domainOf = new Map<string, string>();
  const placed = nodes.map((node) => {
    const category = categoryOf.get(node.id);
    const domain =
      domainByConcept.get(normalizeConceptKey(node.label)) ??
      (category ? domainByCategory.get(category) : undefined) ??
      (node.kind === "measure" ? metricsDomain : undefined) ??
      OTHER_DOMAIN;
    domainOf.set(node.id, domain.id);
    return { ...node, cluster: domain.id, clusterColor: domain.color };
  });

  const degrees = new Map<string, number>();
  for (const edge of edges) {
    degrees.set(edge.source, (degrees.get(edge.source) ?? 0) + 1);
    degrees.set(edge.target, (degrees.get(edge.target) ?? 0) + 1);
  }
  const finalNodes = placed.map((node) => ({ ...node, degree: degrees.get(node.id) ?? 0 }));

  const crossEdges = new Set<string>();
  const bridgeCounts = new Map<string, number>();
  for (const edge of edges) {
    const a = domainOf.get(edge.source);
    const b = domainOf.get(edge.target);
    if (!a || !b || a === b) continue;
    crossEdges.add(edge.id);
    const key = [a, b].sort().join("|");
    bridgeCounts.set(key, (bridgeCounts.get(key) ?? 0) + 1);
  }
  const bridges = [...bridgeCounts.entries()]
    .map(([key, count]) => {
      const [from, to] = key.split("|") as [string, string];
      return { from, to, count };
    })
    .sort((a, b) => b.count - a.count);

  const domains = [...config.domains, OTHER_DOMAIN].filter((domain) =>
    finalNodes.some((node) => node.cluster === domain.id),
  );

  return {
    graph: {
      ...snapshot,
      nodes: finalNodes,
      edges,
      clusters: domains.map((domain) => ({ id: domain.id, label: domain.label, color: domain.color })),
      metadata: { ...snapshot.metadata, nodeCount: finalNodes.length, edgeCount: edges.length },
    },
    domains,
    domainOf,
    crossEdges,
    bridges,
  };
}

/**
 * Centrality blending reach (degree) and influence (PageRank), normalised to [0, 1].
 * Sub-type links (SUV is a kind of Car Type) are left out so a long list of values does not
 * make a classifier look more central than the business entities themselves.
 */
export function ontologyCentrality(graph: OntologySnapshot): Map<string, number> {
  const ids = graph.nodes.map((node) => node.id);
  const links = graph.edges
    .filter((edge) => edge.label !== TAXONOMY_LABEL)
    .map((edge) => ({ source: edge.source, target: edge.target }));
  const degree = degreeCentrality(ids, links);
  const rank = pageRank(ids, links);
  const blended = new Map(ids.map((id) => [id, 0.5 * (degree.get(id) ?? 0) + 0.5 * (rank.get(id) ?? 0)]));
  const max = Math.max(1e-9, ...blended.values());
  for (const [id, value] of blended) blended.set(id, value / max);
  return blended;
}

/** The most central concepts: the ones leadership should notice first. */
export function coreConcepts(graph: OntologySnapshot, limit = 5): string[] {
  const centrality = ontologyCentrality(graph);
  return [...graph.nodes]
    .sort((a, b) => (centrality.get(b.id) ?? 0) - (centrality.get(a.id) ?? 0) || a.label.localeCompare(b.label))
    .slice(0, limit)
    .map((node) => node.id);
}

type SimNode = SimulationNodeDatum & { id: string; domain: string; radius: number; halfWidth: number; score: number };

function domainAnchors(domains: BusinessDomain[], spread: number): Map<string, { x: number; y: number }> {
  const anchors = new Map<string, { x: number; y: number }>();
  const radius = domains.length <= 1 ? 0 : 360 * spread;
  domains.forEach((domain, index) => {
    const angle = -Math.PI / 2 + (index / Math.max(1, domains.length)) * Math.PI * 2;
    anchors.set(domain.id, { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius });
  });
  return anchors;
}

function nodeRadius(style: OntologyMapStyle, score: number): number {
  if (style === "centrality") return 13 + Math.pow(score, 0.9) * 34;
  return 16 + score * 14;
}

function layoutForce(map: OntologyMap, style: OntologyMapStyle, centrality: Map<string, number>): PositionedNode[] {
  const { graph } = map;
  const spread = Math.max(1, Math.sqrt(graph.nodes.length / 20));
  const anchors = domainAnchors(map.domains, spread);
  const anchorOf = (domain: string) => anchors.get(domain) ?? { x: 0, y: 0 };
  // Central concepts drift from their domain towards the shared middle of the map.
  const pullToCore = style === "centrality" ? 0.75 : 0.15;
  const target = (d: SimNode) => {
    const home = anchorOf(d.domain);
    const toward = 1 - d.score * pullToCore;
    return { x: home.x * toward, y: home.y * toward };
  };

  const nodes: SimNode[] = graph.nodes.map((node, index) => {
    const score = centrality.get(node.id) ?? 0;
    const radius = nodeRadius(style, score);
    const home = anchorOf(map.domainOf.get(node.id) ?? "other");
    const angle = (index / Math.max(1, graph.nodes.length)) * Math.PI * 2 * 7;
    return {
      id: node.id,
      domain: map.domainOf.get(node.id) ?? "other",
      radius,
      halfWidth: Math.max(radius, captionWidth(node.label) / 2),
      score,
      x: home.x + Math.cos(angle) * 60,
      y: home.y + Math.sin(angle) * 60,
    };
  });

  const links = graph.edges.map((edge) => ({
    source: edge.source,
    target: edge.target,
    cross: map.crossEdges.has(edge.id),
  }));

  const simulation = forceSimulation(nodes)
    .force(
      "link",
      forceLink<SimNode, (typeof links)[number]>(links)
        .id((d) => d.id)
        .distance((link) => (link.cross ? 230 : 120))
        .strength((link) => (link.cross ? 0.04 : 0.45)),
    )
    .force("charge", forceManyBody().strength(-520).distanceMax(700))
    .force(
      "collide",
      forceCollide<SimNode>()
        .radius((d) => Math.max(d.halfWidth, d.radius + CAPTION_HEIGHT / 2) + 18)
        .iterations(4),
    )
    .force("x", forceX<SimNode>((d) => target(d).x).strength(0.16))
    .force("y", forceY<SimNode>((d) => target(d).y).strength(0.16))
    .stop();

  const ticks = Math.min(500, 220 + nodes.length * 6);
  for (let i = 0; i < ticks; i += 1) simulation.tick();

  const byId = new Map(graph.nodes.map((node) => [node.id, node]));
  return resolveOverlaps(
    nodes.map((sim) => {
      const source = byId.get(sim.id)!;
      return {
        ...source,
        x: sim.x ?? 0,
        y: sim.y ?? 0,
        radius: sim.radius,
        centrality: sim.score,
        captionWidth: captionWidth(source.label),
      };
    }),
  );
}

const MAX_ROW = 4;

/** Each domain is a small tree: its most central concept on top, then one row per step away. */
function layoutDomainTrees(map: OntologyMap, centrality: Map<string, number>): PositionedNode[] {
  const { graph } = map;
  const neighbours = new Map<string, string[]>();
  for (const node of graph.nodes) neighbours.set(node.id, []);
  for (const edge of graph.edges) {
    if (map.crossEdges.has(edge.id)) continue;
    neighbours.get(edge.source)?.push(edge.target);
    neighbours.get(edge.target)?.push(edge.source);
  }

  const rowHeight = 130;
  const columnGap = 140;
  const placed: PositionedNode[] = [];
  let cursorX = 0;
  for (const domain of map.domains) {
    const members = graph.nodes
      .filter((node) => map.domainOf.get(node.id) === domain.id)
      .sort((a, b) => (centrality.get(b.id) ?? 0) - (centrality.get(a.id) ?? 0) || a.label.localeCompare(b.label));
    if (!members.length) continue;
    const depth = new Map<string, number>([[members[0]!.id, 0]]);
    const queue = [members[0]!.id];
    while (queue.length) {
      const id = queue.shift()!;
      for (const next of neighbours.get(id) ?? []) {
        if (depth.has(next) || map.domainOf.get(next) !== domain.id) continue;
        depth.set(next, depth.get(id)! + 1);
        queue.push(next);
      }
    }
    const deepest = Math.max(0, ...depth.values());
    const rows = new Map<number, OntologyNode[]>();
    for (const node of members) {
      const row = depth.get(node.id) ?? deepest + 1;
      rows.set(row, [...(rows.get(row) ?? []), node]);
    }
    const slot = Math.max(...members.map((node) => captionWidth(node.label))) + 28;
    const lines = [...rows.keys()]
      .sort((a, b) => a - b)
      .flatMap((row) => {
        const rowNodes = rows.get(row)!;
        const chunks: OntologyNode[][] = [];
        for (let start = 0; start < rowNodes.length; start += MAX_ROW) {
          chunks.push(rowNodes.slice(start, start + MAX_ROW));
        }
        return chunks;
      });
    const width = Math.max(...lines.map((line) => line.length)) * slot;
    const centreX = cursorX + width / 2;
    lines.forEach((line, lineIndex) => {
      const offset = ((line.length - 1) * slot) / 2;
      line.forEach((node, index) => {
        const score = centrality.get(node.id) ?? 0;
        placed.push({
          ...node,
          x: centreX + index * slot - offset,
          y: lineIndex * rowHeight,
          radius: nodeRadius("hierarchy", score),
          centrality: score,
          captionWidth: captionWidth(node.label),
        });
      });
    });
    cursorX += width + columnGap;
  }
  const shift = cursorX / 2;
  return placed.map((node) => ({ ...node, x: node.x - shift }));
}

export function layoutOntologyMap(map: OntologyMap, style: OntologyMapStyle): PositionedNode[] {
  const centrality = ontologyCentrality(map.graph);
  if (style === "hierarchy") return layoutDomainTrees(map, centrality);
  return layoutForce(map, style, centrality);
}

export type OntologySearchResult = {
  matches: Set<string>;
  /** Matches, their neighbours, and the concepts on the way to the core of the business. */
  related: Set<string>;
  edges: Set<string>;
};

/**
 * "SUV" highlights SUV, what it is a kind of, and the shortest route from it to each core
 * concept, e.g. SUV → Car Type → Vehicle → Sales Transaction → Revenue.
 */
export function searchOntology(graph: OntologySnapshot, query: string, cores: string[]): OntologySearchResult | null {
  const q = normalizeConceptKey(query);
  if (!q) return null;
  // Short queries ("EV", "MG") must match a whole word, or "ev" would hit "revenue".
  const hits = (name: string) => {
    const key = normalizeConceptKey(name);
    return q.length <= 3 ? key.split(" ").includes(q) : key.includes(q);
  };
  const matches = new Set(
    graph.nodes
      .filter((node) => hits(node.label) || node.synonyms.some(hits))
      .map((node) => node.id),
  );
  const related = new Set(matches);
  const edges = new Set<string>();
  if (!matches.size) return { matches, related, edges };

  const adjacency = new Map<string, Array<{ id: string; edge: string }>>();
  for (const edge of graph.edges) {
    adjacency.set(edge.source, [...(adjacency.get(edge.source) ?? []), { id: edge.target, edge: edge.id }]);
    adjacency.set(edge.target, [...(adjacency.get(edge.target) ?? []), { id: edge.source, edge: edge.id }]);
  }
  for (const id of matches) {
    for (const next of adjacency.get(id) ?? []) {
      related.add(next.id);
      edges.add(next.edge);
    }
    const previous = new Map<string, { id: string; edge: string } | null>([[id, null]]);
    const queue = [id];
    while (queue.length) {
      const current = queue.shift()!;
      for (const next of adjacency.get(current) ?? []) {
        if (previous.has(next.id)) continue;
        previous.set(next.id, { id: current, edge: next.edge });
        queue.push(next.id);
      }
    }
    for (const core of cores) {
      let step = previous.get(core);
      if (step === undefined) continue;
      related.add(core);
      let at = core;
      while (step) {
        edges.add(step.edge);
        related.add(step.id);
        at = step.id;
        step = previous.get(at) ?? null;
      }
    }
  }
  return { matches, related, edges };
}
