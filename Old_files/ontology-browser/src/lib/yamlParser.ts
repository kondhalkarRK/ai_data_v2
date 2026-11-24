/**
 * YAML → OntologyGraph parser.
 * Reads ASK-DB semantic_model + business_glossary only.
 * Does not call or alter the Python semantic engine.
 */
import yaml from "js-yaml";
import {
  CLUSTER_PALETTE,
  type ClusterMeta,
  type ColumnMeta,
  type OntologyEdgeData,
  type OntologyGraph,
  type OntologyNodeData,
} from "./types";

type YamlMap = Record<string, unknown>;

function asMap(value: unknown): YamlMap {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as YamlMap)
    : {};
}

function asString(value: unknown, fallback = ""): string {
  if (value == null) return fallback;
  return String(value);
}

function asStringList(value: unknown): string[] {
  if (!value) return [];
  if (Array.isArray(value)) return value.map((v) => String(v));
  return [String(value)];
}

function parseColumns(raw: unknown): ColumnMeta[] {
  const map = asMap(raw);
  return Object.entries(map).map(([name, meta]) => {
    const m = asMap(meta);
    return {
      name,
      displayName: asString(m.display_name, name),
      type: asString(m.type, "unknown"),
      role: asString(m.role, "attribute"),
      references: m.references ? asString(m.references) : undefined,
    };
  });
}

function glossarySynonymsByMeasure(glossaryDoc: YamlMap): Map<string, string[]> {
  const out = new Map<string, string[]>();
  const terms = asMap(glossaryDoc.terms);
  for (const [, termRaw] of Object.entries(terms)) {
    const term = asMap(termRaw);
    const synonyms = asStringList(term.synonyms);
    const measure = asString(term.maps_to_measure);
    if (measure) {
      const prev = out.get(`measure:${measure}`) ?? [];
      out.set(`measure:${measure}`, Array.from(new Set([...prev, ...synonyms])));
    }
  }
  return out;
}

function glossaryTermIndex(glossaryDoc: YamlMap): Map<string, YamlMap> {
  const out = new Map<string, YamlMap>();
  const terms = asMap(glossaryDoc.terms);
  for (const [name, termRaw] of Object.entries(terms)) {
    out.set(name.toLowerCase(), { name, ...asMap(termRaw) });
  }
  return out;
}

function findGlossaryForLabel(
  label: string,
  index: Map<string, YamlMap>,
): YamlMap | null {
  const key = label.toLowerCase();
  if (index.has(key)) return index.get(key)!;
  for (const [k, v] of index.entries()) {
    if (k.includes(key) || key.includes(k)) return v;
  }
  return null;
}

function clusterFor(
  kind: OntologyNodeData["kind"],
  tableType?: string,
): { cluster: string; clusterColor: string } {
  if (kind === "domain") return { cluster: "Domain", clusterColor: CLUSTER_PALETTE.Domain };
  if (kind === "entity") return { cluster: "Entities", clusterColor: CLUSTER_PALETTE.Entities };
  if (kind === "measure") return { cluster: "Measures", clusterColor: CLUSTER_PALETTE.Measures };
  if (kind === "dimension") return { cluster: "Metrics", clusterColor: CLUSTER_PALETTE.Metrics };
  if (tableType === "fact") return { cluster: "Facts", clusterColor: CLUSTER_PALETTE.Facts };
  if (tableType === "dimension") {
    return { cluster: "Dimensions", clusterColor: CLUSTER_PALETTE.Dimensions };
  }
  return { cluster: "Other", clusterColor: CLUSTER_PALETTE.Other };
}

export function parseSemanticYaml(
  modelText: string,
  glossaryText?: string | null,
): OntologyGraph {
  const model = asMap(yaml.load(modelText));
  const glossary = glossaryText ? asMap(yaml.load(glossaryText)) : {};

  const domain = asString(model.domain, "Unknown Domain");
  const description = asString(model.description, "");
  const version = asString(model.version, "");

  const synonymBag = glossarySynonymsByMeasure(glossary);
  const termIndex = glossaryTermIndex(glossary);

  const nodes: OntologyNodeData[] = [];
  const edges: OntologyEdgeData[] = [];
  const nodeIds = new Set<string>();

  const ensureNode = (node: OntologyNodeData) => {
    if (nodeIds.has(node.id)) return;
    nodeIds.add(node.id);
    nodes.push(node);
  };

  const domainId = `domain:${domain}`;
  const domainCluster = clusterFor("domain");
  ensureNode({
    id: domainId,
    label: domain,
    kind: "domain",
    domain,
    description: description || `${domain} semantic model`,
    synonyms: [],
    tables: [],
    columns: [],
    relationships: [],
    lineage: [],
    degree: 0,
    ...domainCluster,
  });

  const tables = asMap(model.tables);
  for (const [tableId, tableRaw] of Object.entries(tables)) {
    const t = asMap(tableRaw);
    const columns = parseColumns(t.columns);
    const display = asString(t.display_name, tableId);
    const gloss = findGlossaryForLabel(display, termIndex);
    const synonyms = gloss ? asStringList(gloss.synonyms) : [];
    const tableType = asString(t.type, "table");
    const cl = clusterFor("table", tableType);

    ensureNode({
      id: `table:${tableId}`,
      label: display,
      kind: "table",
      domain,
      description: asString(t.description, asString(t.grain)),
      physicalName: asString(t.physical_name, tableId),
      tableType,
      grain: asString(t.grain),
      primaryKey: asString(t.primary_key),
      synonyms,
      tables: [asString(t.physical_name, tableId)],
      columns,
      relationships: [],
      lineage: columns
        .filter((c) => c.references)
        .map((c) => `${tableId}.${c.name} → ${c.references}`),
      degree: 0,
      category: tableType,
      raw: t,
      ...cl,
    });

    edges.push({
      id: `dep:${domainId}->table:${tableId}`,
      source: domainId,
      target: `table:${tableId}`,
      kind: "dependency",
      label: "contains",
    });

    for (const col of columns) {
      if (!col.references) continue;
      const targetTable = col.references.split(".")[0];
      if (!tables[targetTable]) continue;
      edges.push({
        id: `ref:${tableId}.${col.name}->${col.references}`,
        source: `table:${tableId}`,
        target: `table:${targetTable}`,
        kind: "reference",
        label: col.name,
        fromColumn: col.name,
        toColumn: col.references.split(".")[1],
        cardinality: "fk",
      });
    }
  }

  const rels = Array.isArray(model.relationships) ? model.relationships : [];
  for (const relRaw of rels) {
    const rel = asMap(relRaw);
    const fromTable = asString(rel.from_table);
    const toTable = asString(rel.to_table);
    if (!fromTable || !toTable) continue;
    if (!nodeIds.has(`table:${fromTable}`)) {
      ensureNode({
        id: `table:${fromTable}`,
        label: fromTable,
        kind: "table",
        domain,
        synonyms: [],
        tables: [fromTable],
        columns: [],
        relationships: [],
        lineage: [],
        degree: 0,
        ...clusterFor("table"),
      });
    }
    if (!nodeIds.has(`table:${toTable}`)) {
      ensureNode({
        id: `table:${toTable}`,
        label: toTable,
        kind: "table",
        domain,
        synonyms: [],
        tables: [toTable],
        columns: [],
        relationships: [],
        lineage: [],
        degree: 0,
        ...clusterFor("table"),
      });
    }
    const name = asString(rel.name, `${fromTable}_to_${toTable}`);
    const display = asString(rel.display_name, name);
    edges.push({
      id: `rel:${name}`,
      source: `table:${fromTable}`,
      target: `table:${toTable}`,
      kind: "relationship",
      label: display,
      fromColumn: asString(rel.from_column) || undefined,
      toColumn: asString(rel.to_column) || undefined,
      cardinality: asString(rel.type, "many_to_one"),
    });
  }

  const entities = Array.isArray(model.business_entities)
    ? model.business_entities
    : [];
  for (const entRaw of entities) {
    const ent = asMap(entRaw);
    const name = asString(ent.name, "Entity");
    const table = asString(ent.table);
    const id = `entity:${name}`;
    const gloss = findGlossaryForLabel(name, termIndex);
    ensureNode({
      id,
      label: name,
      kind: "entity",
      domain,
      description: asString(ent.description),
      synonyms: gloss ? asStringList(gloss.synonyms) : [],
      tables: table ? [table] : [],
      columns: [],
      relationships: [],
      lineage: table ? [`entity:${name} → table:${table}`] : [],
      degree: 0,
      raw: ent,
      ...clusterFor("entity"),
    });
    edges.push({
      id: `dep:${domainId}->${id}`,
      source: domainId,
      target: id,
      kind: "dependency",
      label: "entity",
    });
    if (table && nodeIds.has(`table:${table}`)) {
      edges.push({
        id: `maps:${id}->table:${table}`,
        source: id,
        target: `table:${table}`,
        kind: "maps_to",
        label: "maps to",
      });
    }
  }

  const measures = asMap(model.measures);
  for (const [measureId, measureRaw] of Object.entries(measures)) {
    const m = asMap(measureRaw);
    const display = asString(m.display_name, measureId);
    const sourceTable = asString(m.source_table);
    const synFromModel = asStringList(m.synonyms);
    const synFromGloss = synonymBag.get(`measure:${measureId}`) ?? [];
    const synonyms = Array.from(new Set([...synFromModel, ...synFromGloss]));
    const id = `measure:${measureId}`;
    ensureNode({
      id,
      label: display,
      kind: "measure",
      domain,
      description: asString(m.description, asString(m.expression)),
      synonyms,
      tables: sourceTable ? [sourceTable] : [],
      columns: [],
      relationships: [],
      lineage: sourceTable
        ? [`${display} ← ${sourceTable}.${asString(m.source_column)}`]
        : [],
      degree: 0,
      category: asString(m.format),
      raw: m,
      ...clusterFor("measure"),
    });
    if (sourceTable && nodeIds.has(`table:${sourceTable}`)) {
      edges.push({
        id: `maps:${id}->table:${sourceTable}`,
        source: id,
        target: `table:${sourceTable}`,
        kind: "maps_to",
        label: "sourced from",
      });
    }
  }

  const dimensions = asMap(model.dimensions);
  for (const [dimName, dimRaw] of Object.entries(dimensions)) {
    const d = asMap(dimRaw);
    const display = asString(d.display_name, dimName);
    const sourceTable = asString(d.source_table);
    const id = `dimension:${dimName}`;
    ensureNode({
      id,
      label: display,
      kind: "dimension",
      domain,
      description: `Semantic dimension · ${asString(d.type, "attribute")}`,
      synonyms: asStringList(d.synonyms),
      tables: sourceTable ? [sourceTable] : [],
      columns: asStringList(d.attributes).map((a) => ({
        name: a,
        displayName: a,
        type: "attribute",
        role: "attribute",
      })),
      relationships: [],
      lineage: sourceTable
        ? [`${display} ← ${sourceTable}.${asString(d.source_column)}`]
        : [],
      degree: 0,
      raw: d,
      ...clusterFor("dimension"),
    });
    if (sourceTable && nodeIds.has(`table:${sourceTable}`)) {
      edges.push({
        id: `maps:${id}->table:${sourceTable}`,
        source: id,
        target: `table:${sourceTable}`,
        kind: "maps_to",
        label: "sourced from",
      });
    }
  }

  const edgeMap = new Map<string, OntologyEdgeData>();
  for (const e of edges) {
    if (e.source === e.target) continue;
    if (!nodeIds.has(e.source) || !nodeIds.has(e.target)) continue;
    if (!edgeMap.has(e.id)) edgeMap.set(e.id, e);
  }
  const uniqueEdges = Array.from(edgeMap.values());

  const degree = new Map<string, number>();
  const relNames = new Map<string, string[]>();
  for (const e of uniqueEdges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
    const listS = relNames.get(e.source) ?? [];
    listS.push(`${e.label} → ${e.target.replace(/^[^:]+:/, "")}`);
    relNames.set(e.source, listS);
    const listT = relNames.get(e.target) ?? [];
    listT.push(`${e.label} ← ${e.source.replace(/^[^:]+:/, "")}`);
    relNames.set(e.target, listT);
  }

  for (const n of nodes) {
    n.degree = degree.get(n.id) ?? 0;
    n.relationships = relNames.get(n.id) ?? [];
  }

  const clusterIds = Array.from(new Set(nodes.map((n) => n.cluster)));
  const clusters: ClusterMeta[] = clusterIds.map((id) => ({
    id,
    label: id,
    color: CLUSTER_PALETTE[id] ?? CLUSTER_PALETTE.Other,
  }));

  return {
    domain,
    description,
    version,
    nodes,
    edges: uniqueEdges,
    clusters,
  };
}

export async function loadPackGraph(
  modelUrl: string,
  glossaryUrl?: string | null,
): Promise<OntologyGraph> {
  const modelRes = await fetch(modelUrl);
  if (!modelRes.ok) {
    throw new Error(`Failed to load semantic model: ${modelUrl}`);
  }
  const modelText = await modelRes.text();
  let glossaryText: string | null = null;
  if (glossaryUrl) {
    const gRes = await fetch(glossaryUrl);
    if (gRes.ok) glossaryText = await gRes.text();
  }
  return parseSemanticYaml(modelText, glossaryText);
}
