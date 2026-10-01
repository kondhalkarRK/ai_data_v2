import type {
  GlossaryTerm,
  SemanticDimension,
  SemanticMeasure,
  SemanticPackResponse,
  SemanticTable,
} from "@nql/shared-types";

import type { EntityRow } from "@/lib/entity-catalog/types";

export interface ExampleQuestion {
  text: string;
  curated: boolean;
}

export interface TableRef {
  name: string;
  displayName: string;
}

export interface MeasureEntry {
  id: string;
  name: string;
  category: string;
  definition: string;
  definitionGoverned: boolean;
  businessFormula: string;
  sqlExpression: string;
  aggregationLabel: string;
  formatLabel: string;
  sourceTables: TableRef[];
  sourceColumns: TableRef[];
  synonyms: string[];
  dimensionIds: string[];
  /** Descriptive columns on the measure's own table, for measures with no governed joins. */
  localBreakdowns: string[];
  joinPaths: Record<string, string[]>;
  rules: string[];
  examples: ExampleQuestion[];
}

export interface DerivedMetricEntry {
  id: string;
  name: string;
  category: string;
  definition: string;
  synonyms: string[];
  rules: string[];
  examples: ExampleQuestion[];
  available: boolean;
  appliesTo: string[];
}

export interface DimensionValue {
  value: string;
  aliases: string[];
}

export interface AttributeEntry {
  id: string;
  dimensionId: string;
  name: string;
  description: string;
  definitionGoverned: boolean;
  synonyms: string[];
  values: DimensionValue[];
  distinctValues: number | null;
  aiResolvable: boolean;
  source: TableRef;
  column: string;
}

export interface DimensionEntry {
  id: string;
  name: string;
  type: string;
  definition: string;
  definitionGoverned: boolean;
  aliases: string[];
  source: TableRef;
  attributes: AttributeEntry[];
  hierarchy: { name: string; levels: string[] } | null;
  examples: ExampleQuestion[];
  synthetic: boolean;
}

export type UnderstandingKind =
  | "Measure"
  | "Metric"
  | "Dimension"
  | "Attribute"
  | "Value filter"
  | "Value"
  | "Not available";

export interface UnderstandingTarget {
  label: string;
  kind: UnderstandingKind;
  detail?: string;
  attrId?: string;
}

export interface UnderstandingRow {
  key: string;
  terms: string[];
  targets: UnderstandingTarget[];
  sources: string[];
  ambiguous: boolean;
}

export interface CoverageGap {
  label: string;
  kind: "Measure" | "Dimension" | "Attribute";
  missing: string[];
}

export interface CoverageSummary {
  measures: number;
  derivedMetrics: number;
  dimensions: number;
  attributes: number;
  relationships: number;
  joins: number;
  businessTerms: number;
  aliases: number;
  valueSynonyms: number;
  aiCoverage: number;
  coveredConcepts: number;
  totalConcepts: number;
  gaps: CoverageGap[];
}

export interface GovernanceRules {
  always: string[];
  never: string[];
}

export interface BusinessSemanticLayer {
  domain: string;
  version: string;
  measures: MeasureEntry[];
  derived: DerivedMetricEntry[];
  dimensions: DimensionEntry[];
  understanding: UnderstandingRow[];
  coverage: CoverageSummary;
  hierarchies: Array<{ name: string; levels: string[] }>;
  rules: GovernanceRules;
}

const AGGREGATION_LABELS: Record<string, string> = {
  sum: "Sum",
  count: "Count",
  count_distinct: "Distinct count",
  avg: "Average",
  average: "Average",
  ratio: "Ratio",
  min: "Minimum",
  max: "Maximum",
};

const FORMAT_LABELS: Record<string, string> = {
  currency: "Currency (₹)",
  integer: "Count",
  percent: "Percentage",
  decimal: "Decimal",
};

const ADDITIVE = new Set(["sum", "count", "count_distinct"]);

const PLURALS: Record<string, string> = {
  salesperson: "salespeople",
  person: "people",
  policy: "policies",
  country: "countries",
  city: "cities",
  category: "categories",
};

function unique(values: Iterable<string>): string[] {
  const seen = new Map<string, string>();
  for (const raw of values) {
    const value = raw?.trim();
    if (!value) continue;
    const key = value.toLowerCase();
    if (!seen.has(key)) seen.set(key, value);
  }
  return [...seen.values()];
}

function humanize(identifier: string): string {
  return identifier
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase())
    .replace(/\bId\b/g, "ID");
}

export function pluralize(noun: string): string {
  const lower = noun.toLowerCase();
  if (PLURALS[lower]) return PLURALS[lower];
  if (/(s|x|ch|sh)$/.test(lower)) return `${lower}es`;
  if (/[^aeiou]y$/.test(lower)) return `${lower.slice(0, -1)}ies`;
  return `${lower}s`;
}

function tableRef(pack: SemanticPackResponse, name: string): TableRef {
  return { name, displayName: pack.model.tables[name]?.displayName ?? humanize(name) };
}

function columnLabel(table: SemanticTable | undefined, column: string): string {
  return table?.columns[column]?.displayName ?? humanize(column);
}

function findColumn(
  pack: SemanticPackResponse,
  column: string,
  preferred?: string,
): string | null {
  if (preferred && pack.model.tables[preferred]?.columns[column]) return preferred;
  const tables = Object.entries(pack.model.tables);
  const fact = tables.find(([, table]) => table.type === "fact" && table.columns[column]);
  if (fact) return fact[0];
  return tables.find(([, table]) => table.columns[column])?.[0] ?? null;
}

function expressionColumns(pack: SemanticPackResponse, measure: SemanticMeasure): TableRef[] {
  const found: TableRef[] = [];
  const seen = new Set<string>();
  for (const token of measure.expression.match(/[A-Za-z_][A-Za-z0-9_]*/g) ?? []) {
    const table = findColumn(pack, token, measure.sourceTable);
    if (!table) continue;
    const key = `${table}.${token}`;
    if (seen.has(key)) continue;
    seen.add(key);
    found.push({ name: key, displayName: columnLabel(pack.model.tables[table], token) });
  }
  return found;
}

function businessFormula(pack: SemanticPackResponse, measure: SemanticMeasure): string {
  const label = (column: string) => {
    const table = findColumn(pack, column, measure.sourceTable);
    return table ? columnLabel(pack.model.tables[table], column) : humanize(column);
  };
  const totalOf = (column: string) => {
    const name = label(column);
    return /^total\b/i.test(name) ? name : `Total ${name}`;
  };
  let text = measure.expression
    .replace(/NULLIF\(\s*(.+?)\s*,\s*0\s*\)/gi, "$1")
    .replace(/::\w+/g, "");
  text = text
    .replace(/COUNT\(\s*DISTINCT\s+([A-Za-z_][\w]*)\s*\)/gi, (_, col: string) => `Unique ${label(col)}`)
    .replace(/COUNT\(\s*\*\s*\)\s*FILTER\s*\(\s*WHERE\s+([A-Za-z_][\w]*)\s*\)/gi, (_, col: string) =>
      `Records where ${label(col)}`,
    )
    .replace(/COUNT\(\s*\*\s*\)/gi, "Record count")
    .replace(/SUM\(\s*([A-Za-z_][\w]*)\s*\)/gi, (_, col: string) => totalOf(col))
    .replace(/AVG\(\s*([A-Za-z_][\w]*)\s*\)/gi, (_, col: string) => `Average ${label(col)}`)
    .replace(/MIN\(\s*([A-Za-z_][\w]*)\s*\)/gi, (_, col: string) => `Lowest ${label(col)}`)
    .replace(/MAX\(\s*([A-Za-z_][\w]*)\s*\)/gi, (_, col: string) => `Highest ${label(col)}`)
    .replace(/\s*\/\s*/g, " ÷ ")
    .replace(/\s*\*\s*/g, " × ");
  return text.trim();
}

/** Follow governed many-to-one joins outward from a table; returns the table path to each reachable table. */
function reachableTables(pack: SemanticPackResponse, start: string): Map<string, string[]> {
  const edges = new Map<string, string[]>();
  for (const rel of pack.model.relationships) {
    const type = rel.type.toLowerCase().replace(/[-\s]/g, "_");
    const add = (from: string, to: string) => edges.set(from, [...(edges.get(from) ?? []), to]);
    if (type.includes("many_to_one") || type === "n:1") add(rel.fromTable, rel.toTable);
    else if (type.includes("one_to_many") || type === "1:n") add(rel.toTable, rel.fromTable);
    else if (type.includes("one_to_one") || type === "1:1") {
      add(rel.fromTable, rel.toTable);
      add(rel.toTable, rel.fromTable);
    }
  }
  const paths = new Map<string, string[]>([[start, [start]]]);
  const queue = [start];
  while (queue.length) {
    const current = queue.shift()!;
    for (const next of edges.get(current) ?? []) {
      if (paths.has(next)) continue;
      paths.set(next, [...(paths.get(current) ?? []), next]);
      queue.push(next);
    }
  }
  return paths;
}

function glossaryFor(
  pack: SemanticPackResponse,
  match: (term: GlossaryTerm) => boolean,
): Array<[string, GlossaryTerm]> {
  return Object.entries(pack.glossary.terms).filter(([, term]) => match(term));
}

interface ValueFilter {
  attrId: string;
  values: string[];
}

function parseFilter(term: GlossaryTerm): ValueFilter | null {
  const match = term.sqlExpression?.match(
    /([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*(?:=\s*'([^']*)'|IN\s*\(([^)]*)\))/i,
  );
  if (!match) return null;
  const values = match[4] ? [...match[4].matchAll(/'([^']*)'/g)].map((item) => item[1] ?? "") : [match[3] ?? ""];
  const clean = values.filter(Boolean);
  return clean.length ? { attrId: `${match[1]}.${match[2]}`, values: clean } : null;
}

function isValueFilter(term: GlossaryTerm): boolean {
  return parseFilter(term) !== null;
}

/** Title-case words read as ordinary words inside a sentence; acronyms keep their case. */
function phrase(name: string): string {
  return name
    .split(" ")
    .map((word) => (/^[A-Z][a-z]+$/.test(word) ? word.toLowerCase() : word))
    .join(" ");
}

const RANKABLE = /dealer|agent|salesperson|sales rep|branch|broker|store|outlet|region|customer|supplier/i;

function isUnavailable(term: GlossaryTerm): boolean {
  return (
    term.calculationRules.some((rule) => /^not available/i.test(rule.trim())) ||
    /cannot be computed|not available/i.test(term.definition)
  );
}

function mergeExamples(curated: string[], suggested: string[], limit = 5): ExampleQuestion[] {
  const out: ExampleQuestion[] = [];
  const seen = new Set<string>();
  for (const [text, isCurated] of [
    ...curated.map((text) => [text, true] as const),
    ...suggested.map((text) => [text, false] as const),
  ]) {
    const key = text.trim().toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push({ text: text.trim(), curated: isCurated });
    if (out.length >= limit) break;
  }
  return out;
}

export function buildSemanticLayer(
  pack: SemanticPackResponse,
  catalog: EntityRow[] = [],
): BusinessSemanticLayer {
  const model = pack.model;
  const catalogByColumn = new Map(catalog.map((row) => [`${row.table}.${row.column}`, row]));
  const valueDomains = Object.entries(model.valueDomains ?? {});
  const domainByColumn = new Map(valueDomains.map(([key, domain]) => [`${domain.table}.${domain.column}`, { key, domain }]));
  const hierarchies = Object.entries(model.hierarchies ?? {})
    .filter((entry): entry is [string, string[]] => Array.isArray(entry[1]))
    .map(([name, levels]) => ({ name, levels }));
  const levelLabel = (level: string): string => {
    const domain = valueDomains.find(([, d]) => d.column === level)?.[1];
    if (domain) return domain.label;
    for (const table of Object.values(model.tables)) {
      if (table.columns[level]) return table.columns[level].displayName;
    }
    return humanize(level);
  };

  // ---- dimensions ---------------------------------------------------------
  const dimensionByTable = new Map<string, string>();
  for (const [id, dimension] of Object.entries(model.dimensions)) {
    if (dimension.type === "date") continue;
    if (!dimensionByTable.has(dimension.sourceTable)) dimensionByTable.set(dimension.sourceTable, id);
  }

  const attributeColumns = new Map<string, Set<string>>();
  const addAttribute = (table: string, column: string) => {
    if (!model.tables[table]?.columns[column]) return;
    const owner = dimensionByTable.get(table) ?? `table:${table}`;
    const set = attributeColumns.get(owner) ?? new Set<string>();
    set.add(`${table}.${column}`);
    attributeColumns.set(owner, set);
  };
  for (const dimension of Object.values(model.dimensions)) {
    for (const attr of dimension.attributes) addAttribute(dimension.sourceTable, attr);
  }
  for (const [, domain] of valueDomains) addAttribute(domain.table, domain.column);
  for (const [, term] of glossaryFor(pack, (term) => Boolean(term.mapsToAttribute))) {
    const [table, column] = term.mapsToAttribute!.split(".");
    if (table && column) addAttribute(table, column);
  }

  const attributeOf = (key: string, dimensionId: string): AttributeEntry => {
    const [table = "", column = ""] = key.split(".");
    const tableModel = model.tables[table];
    const columnModel = tableModel?.columns[column];
    const domainHit = domainByColumn.get(key);
    const catalogRow = catalogByColumn.get(key);
    const conceptTerms = glossaryFor(pack, (term) => term.mapsToAttribute === key && !isValueFilter(term));
    const filterTerms = glossaryFor(pack, (term) => parseFilter(term)?.attrId === key);
    const definitionTerm = conceptTerms[0]?.[1];
    const name = domainHit?.domain.label ?? columnLabel(tableModel, column);

    const values = new Map<string, DimensionValue>();
    for (const [value, aliases] of Object.entries(domainHit?.domain.valueAliases ?? {})) {
      values.set(value.toLowerCase(), { value, aliases: unique(aliases) });
    }
    for (const [termName, term] of filterTerms) {
      const filter = parseFilter(term)!;
      for (const value of filter.values) {
        const existing = values.get(value.toLowerCase());
        const extra =
          filter.values.length === 1
            ? [termName, ...term.synonyms].filter((alias) => alias.toLowerCase() !== value.toLowerCase())
            : [];
        values.set(value.toLowerCase(), {
          value: existing?.value ?? value,
          aliases: unique([...(existing?.aliases ?? []), ...extra]),
        });
      }
    }
    for (const sample of catalogRow?.sampleValues ?? []) {
      if (!values.has(sample.toLowerCase())) values.set(sample.toLowerCase(), { value: sample, aliases: [] });
    }

    const synonyms = unique([
      ...(domainHit?.domain.aliases ?? []),
      ...(catalogRow?.aliases ?? []),
      ...conceptTerms.flatMap(([termName, term]) => [termName, ...term.synonyms]),
    ]).filter((item) => item.toLowerCase() !== name.toLowerCase());

    return {
      id: key,
      dimensionId,
      name,
      description:
        definitionTerm?.definition.trim() ??
        columnModel?.description ??
        `${name} recorded on each ${tableModel?.displayName ?? humanize(table)} record.`,
      definitionGoverned: Boolean(definitionTerm || columnModel?.description),
      synonyms,
      values: [...values.values()],
      distinctValues: catalogRow?.distinctValues ?? null,
      aiResolvable: Boolean(domainHit || catalogRow?.aiKnown),
      source: tableRef(pack, table),
      column,
    };
  };

  const dimensionType = (dimension: SemanticDimension | null, attrs: AttributeEntry[], fallback: string) => {
    if (dimension?.type === "date") return "Time";
    const groups = new Map<string, number>();
    for (const attr of attrs) {
      const group = catalogByColumn.get(attr.id)?.group;
      if (group) groups.set(group, (groups.get(group) ?? 0) + 1);
    }
    const topGroup = [...groups.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
    if (topGroup) return topGroup;
    const columns = new Set(attrs.map((attr) => attr.column));
    const best = hierarchies
      .map((h) => ({ name: h.name, overlap: h.levels.filter((level) => columns.has(level)).length }))
      .sort((a, b) => b.overlap - a.overlap)[0];
    if (best && best.overlap > 0) return best.name;
    return fallback;
  };

  const hierarchyFor = (attrs: AttributeEntry[]) => {
    const columns = new Set(attrs.map((attr) => attr.column));
    const best = hierarchies
      .map((h) => ({ h, overlap: h.levels.filter((level) => columns.has(level)).length }))
      .sort((a, b) => b.overlap - a.overlap)[0];
    if (!best || best.overlap < 2) return null;
    const labels = new Map(attrs.map((attr) => [attr.column, attr.name]));
    return { name: best.h.name, levels: best.h.levels.map((level) => labels.get(level) ?? levelLabel(level)) };
  };

  const dimensions: DimensionEntry[] = [];
  for (const [id, dimension] of Object.entries(model.dimensions)) {
    const attrs = [...(attributeColumns.get(id) ?? [])].map((key) => attributeOf(key, id));
    const term = glossaryFor(pack, (t) => t.mapsToDimension === id)[0];
    const isDate = dimension.type === "date";
    const entity = isDate ? undefined : model.businessEntities.find((item) => item.table === dimension.sourceTable);
    const definition =
      term?.[1].definition.trim() ??
      entity?.description ??
      (isDate ? undefined : model.tables[dimension.sourceTable]?.description) ??
      (isDate
        ? "Analyse any measure over time: by day, month, quarter or year."
        : `Analyse measures by ${dimension.displayName.toLowerCase()}.`);
    dimensions.push({
      id,
      name: dimension.displayName,
      type: dimensionType(dimension, attrs, term?.[1].category ?? "Attribute"),
      definition,
      definitionGoverned: Boolean(
        term || entity?.description || (!isDate && model.tables[dimension.sourceTable]?.description),
      ),
      aliases: unique([
        ...dimension.synonyms,
        ...(term ? [term[0], ...term[1].synonyms] : []),
      ]).filter((alias) => alias.toLowerCase() !== dimension.displayName.toLowerCase()),
      source: tableRef(pack, dimension.sourceTable),
      attributes: attrs,
      hierarchy: hierarchyFor(attrs),
      examples: [],
      synthetic: false,
    });
  }
  for (const [owner, keys] of attributeColumns) {
    if (!owner.startsWith("table:")) continue;
    const table = owner.slice("table:".length);
    const attrs = [...keys].map((key) => attributeOf(key, owner));
    const ref = tableRef(pack, table);
    const category = glossaryFor(pack, (t) => t.mapsToAttribute?.startsWith(`${table}.`) ?? false)[0]?.[1].category;
    dimensions.push({
      id: owner,
      name: `${ref.displayName.replace(/^fact\s+/i, "")} attributes`,
      type: dimensionType(null, attrs, category ?? "Attribute"),
      definition: model.tables[table]?.description ?? `Descriptive fields recorded directly on ${ref.displayName}.`,
      definitionGoverned: Boolean(model.tables[table]?.description),
      aliases: [],
      source: ref,
      attributes: attrs,
      hierarchy: hierarchyFor(attrs),
      examples: [],
      synthetic: true,
    });
  }

  // ---- measures -----------------------------------------------------------
  const measureColumns = new Set(
    Object.values(model.measures)
      .filter((measure) => measure.sourceTable && measure.sourceColumn)
      .map((measure) => `${measure.sourceTable}.${measure.sourceColumn}`),
  );
  const localBreakdowns = (tables: string[]) =>
    unique(
      tables.flatMap((table) =>
        Object.keys(model.tables[table]?.columns ?? {})
          .filter((column) => !/(^|_)id$/i.test(column) && !measureColumns.has(`${table}.${column}`))
          .map((column) => (/date|month|year|period/i.test(column) ? "Time" : columnLabel(model.tables[table], column))),
      ),
    );

  const measureEntries: MeasureEntry[] = Object.entries(model.measures).map(([id, measure]) => {
    const columns = expressionColumns(pack, measure);
    const tables = unique([
      ...(measure.sourceTable ? [measure.sourceTable] : []),
      ...columns.map((column) => column.name.split(".")[0] ?? ""),
    ]);
    const reach = tables.map((table) => reachableTables(pack, table));
    const joinPaths: Record<string, string[]> = {};
    const dimensionIds = dimensions
      .filter((dimension) => reach.length > 0 && reach.every((paths) => paths.has(dimension.source.name)))
      .map((dimension) => {
        joinPaths[dimension.id] = (reach[0]?.get(dimension.source.name) ?? []).map(
          (table) => tableRef(pack, table).displayName,
        );
        return dimension.id;
      });
    const term = glossaryFor(pack, (t) => t.mapsToMeasure === id)[0];
    const sourceColumns = measure.sourceColumn
      ? [
          {
            name: `${measure.sourceTable}.${measure.sourceColumn}`,
            displayName: columnLabel(model.tables[measure.sourceTable ?? ""], measure.sourceColumn),
          },
        ]
      : columns;
    return {
      id,
      name: measure.displayName,
      category: term?.[1].category ?? "Measure",
      definition:
        term?.[1].definition.trim() ??
        measure.description ??
        `${AGGREGATION_LABELS[measure.aggregation] ?? "Calculated"} of ${sourceColumns.map((c) => c.displayName).join(", ") || measure.displayName}.`,
      definitionGoverned: Boolean(term || measure.description),
      businessFormula: businessFormula(pack, measure),
      sqlExpression: measure.expression,
      aggregationLabel: AGGREGATION_LABELS[measure.aggregation] ?? humanize(measure.aggregation),
      formatLabel: FORMAT_LABELS[measure.format] ?? humanize(measure.format),
      sourceTables: tables.map((table) => tableRef(pack, table)),
      sourceColumns,
      synonyms: unique([...measure.synonyms, ...(term?.[1].synonyms ?? [])]).filter(
        (alias) => alias.toLowerCase() !== measure.displayName.toLowerCase(),
      ),
      dimensionIds,
      localBreakdowns: dimensionIds.length ? [] : localBreakdowns(tables),
      joinPaths,
      rules: unique([...(term?.[1].calculationRules ?? []), ...(term?.[1].disambiguation ?? [])]),
      examples: [],
    };
  });

  const dimensionById = new Map(dimensions.map((dimension) => [dimension.id, dimension]));
  const rankedAttributes = (dimension: DimensionEntry) => {
    const levels = dimension.hierarchy?.levels ?? [];
    const rank = (attr: AttributeEntry) => {
      const index = levels.indexOf(attr.name);
      return index < 0 ? levels.length + 1 : index;
    };
    return [...dimension.attributes].sort((a, b) => rank(a) - rank(b));
  };
  for (const dimension of dimensions) dimension.attributes = rankedAttributes(dimension);
  const sampleValue = (dims: DimensionEntry[]) => {
    for (const dimension of dims) {
      for (const attr of rankedAttributes(dimension)) {
        const value = attr.values.find((item) => item.value.length > 3);
        if (value) return value.value;
      }
    }
    return null;
  };
  const sliceBy = (dimension: DimensionEntry) =>
    phrase(rankedAttributes(dimension).find((attr) => attr.aiResolvable)?.name ?? dimension.name);

  for (const measure of measureEntries) {
    const term = glossaryFor(pack, (t) => t.mapsToMeasure === measure.id)[0]?.[1];
    const dims = measure.dimensionIds.map((id) => dimensionById.get(id)!).filter(Boolean);
    const timeDim = dims.find((dimension) => dimension.type === "Time");
    const businessDims = dims.filter((dimension) => dimension.type !== "Time" && !dimension.synthetic);
    const measureWords = measure.name.toLowerCase();
    const candidates = businessDims.filter(
      (dimension) =>
        !measureWords.includes(dimension.name.toLowerCase()) && !measureWords.includes(pluralize(dimension.name)),
    );
    const rankable =
      candidates.find((dimension) => RANKABLE.test([dimension.name, ...dimension.aliases].join(" "))) ??
      candidates[1];
    const metric = phrase(measure.name);
    const suggestions: string[] = [];
    if (businessDims[0]) suggestions.push(`${measure.name} by ${sliceBy(businessDims[0])}`);
    if (timeDim) suggestions.push(`${measure.name} trend by month`);
    if (rankable) suggestions.push(`Top 10 ${pluralize(rankable.name)} by ${metric}`);
    const sample = sampleValue(businessDims);
    if (sample) suggestions.push(`${measure.name} for ${sample} this year`);
    for (const dimension of businessDims.slice(1)) {
      if (dimension !== rankable) suggestions.push(`${measure.name} by ${sliceBy(dimension)}`);
    }
    if (!dims.length) suggestions.push(`Total ${metric}`, `${measure.name} this year`);
    measure.examples = mergeExamples(term?.exampleQuestions ?? [], suggestions);
  }

  for (const dimension of dimensions) {
    const term = dimension.synthetic
      ? undefined
      : glossaryFor(pack, (t) => t.mapsToDimension === dimension.id)[0]?.[1];
    const attrTerms = dimension.attributes.flatMap((attr) =>
      glossaryFor(pack, (t) => t.mapsToAttribute === attr.id && !isValueFilter(t)).flatMap(([, t]) => t.exampleQuestions),
    );
    const measure = measureEntries.find((item) => item.dimensionIds.includes(dimension.id));
    const suggestions: string[] = [];
    if (measure) {
      const metric = phrase(measure.name);
      if (dimension.type === "Time") {
        suggestions.push(`${measure.name} by month`, `${measure.name} year over year`);
      } else {
        const resolvable = rankedAttributes(dimension).filter((attr) => attr.aiResolvable || attr.values.length);
        for (const attr of resolvable.slice(0, 2)) suggestions.push(`${measure.name} by ${phrase(attr.name)}`);
        const sample = sampleValue([dimension]);
        if (sample) suggestions.push(`${measure.name} for ${sample}`);
        if (!dimension.synthetic) suggestions.push(`Top 5 ${pluralize(dimension.name)} by ${metric}`);
      }
    }
    dimension.examples = mergeExamples([...(term?.exampleQuestions ?? []), ...attrTerms], suggestions);
  }

  // ---- derived / unavailable metrics ---------------------------------------
  const additive = measureEntries
    .filter((measure) => ADDITIVE.has(model.measures[measure.id]?.aggregation ?? ""))
    .map((measure) => measure.id);
  const derived: DerivedMetricEntry[] = glossaryFor(
    pack,
    (term) => !term.mapsToMeasure && !term.mapsToDimension && !term.mapsToAttribute,
  ).map(([name, term]) => {
    const available = !isUnavailable(term);
    const label = term.displayLabel ?? name;
    const suggested = available
      ? additive
          .slice(0, 2)
          .map((id) => `${model.measures[id]?.displayName ?? humanize(id)} ${phrase(label)} by year`)
      : [];
    return {
      id: `term:${name}`,
      name: label,
      category: term.category,
      definition: term.definition.trim(),
      synonyms: unique(term.synonyms),
      rules: unique([...term.calculationRules, ...term.disambiguation]),
      examples: mergeExamples(term.exampleQuestions, suggested, 4),
      available,
      appliesTo: available ? additive : [],
    };
  });

  // ---- AI understanding ---------------------------------------------------
  const termMap = new Map<string, { term: string; targets: Map<string, UnderstandingTarget>; sources: Set<string> }>();
  const attributeById = new Map(dimensions.flatMap((d) => d.attributes).map((attr) => [attr.id, attr]));
  const learn = (rawTerm: string, target: UnderstandingTarget, source: string) => {
    const term = rawTerm.trim();
    if (!term) return;
    const key = term.toLowerCase();
    const entry = termMap.get(key) ?? { term, targets: new Map(), sources: new Set() };
    entry.targets.set(`${target.kind}:${target.label.toLowerCase()}`, target);
    entry.sources.add(source);
    termMap.set(key, entry);
  };
  const attrLabel = (attrId: string) =>
    attributeById.get(attrId)?.name ?? humanize(attrId.split(".")[1] ?? attrId);

  for (const measure of Object.values(model.measures)) {
    for (const synonym of measure.synonyms) learn(synonym, { label: measure.displayName, kind: "Measure" }, "Semantic model");
  }
  for (const [id, dimension] of Object.entries(model.dimensions)) {
    for (const synonym of dimension.synonyms) {
      learn(synonym, { label: dimension.displayName, kind: "Dimension", detail: id }, "Semantic model");
    }
  }
  for (const [termName, term] of Object.entries(pack.glossary.terms)) {
    const words = [termName, ...term.synonyms];
    const filter = parseFilter(term);
    let target: UnderstandingTarget | null = null;
    if (filter) {
      const label = attrLabel(filter.attrId);
      target = {
        label: filter.values.length === 1 ? `${label} = ${filter.values[0]}` : `${label} in ${filter.values.join(", ")}`,
        kind: "Value filter",
        attrId: filter.attrId,
      };
    } else if (term.mapsToMeasure) {
      target = { label: model.measures[term.mapsToMeasure]?.displayName ?? humanize(term.mapsToMeasure), kind: "Measure" };
    } else if (term.mapsToDimension) {
      target = {
        label: model.dimensions[term.mapsToDimension]?.displayName ?? term.mapsToDimension,
        kind: "Dimension",
        detail: term.mapsToDimension,
      };
    } else if (term.mapsToAttribute) {
      target = { label: attrLabel(term.mapsToAttribute), kind: "Attribute", attrId: term.mapsToAttribute };
    } else {
      target = isUnavailable(term)
        ? { label: term.displayLabel ?? termName, kind: "Not available", detail: term.calculationRules[0] ?? term.definition }
        : { label: term.displayLabel ?? termName, kind: "Metric" };
    }
    for (const word of words) learn(word, target, "Business glossary");
  }
  for (const [, domain] of valueDomains) {
    const key = `${domain.table}.${domain.column}`;
    const label = attrLabel(key);
    for (const alias of domain.aliases) learn(alias, { label, kind: "Attribute", attrId: key }, "Value dictionary");
    for (const [value, aliases] of Object.entries(domain.valueAliases)) {
      for (const alias of aliases) {
        learn(alias, { label: value, kind: "Value", detail: label, attrId: key }, "Value dictionary");
      }
    }
  }

  const grouped = new Map<string, UnderstandingRow>();
  for (const entry of termMap.values()) {
    let targets = [...entry.targets.values()];
    const filtered = new Set(targets.filter((t) => t.kind === "Value filter").map((t) => t.attrId));
    targets = targets.filter((t) => !(t.kind === "Value" && filtered.has(t.attrId)));
    const valuesByAttr = new Map<string, UnderstandingTarget[]>();
    for (const t of targets) {
      if (t.kind === "Value" && t.attrId) valuesByAttr.set(t.attrId, [...(valuesByAttr.get(t.attrId) ?? []), t]);
    }
    for (const [attrId, values] of valuesByAttr) {
      if (values.length < 2) continue;
      targets = targets.filter((t) => !(t.kind === "Value" && t.attrId === attrId));
      targets.push({
        label: `${attrLabel(attrId)} in ${values.map((v) => v.label).join(", ")}`,
        kind: "Value filter",
        attrId,
      });
    }
    const valueAttrs = new Set(targets.filter((t) => t.kind !== "Attribute" && t.attrId).map((t) => t.attrId));
    targets = targets.filter((t) => !(t.kind === "Attribute" && valueAttrs.has(t.attrId)));
    const ownedDims = new Set(
      targets.map((t) => (t.attrId ? attributeById.get(t.attrId)?.dimensionId : undefined)).filter(Boolean),
    );
    targets = targets.filter((t) => !(t.kind === "Dimension" && ownedDims.has(t.detail)));
    const term = entry.term.toLowerCase();
    if (!targets.length || targets.every((t) => t.label.toLowerCase() === term)) continue;
    targets.sort((a, b) => a.label.localeCompare(b.label));
    const key = targets.map((t) => `${t.kind}:${t.label}`).join("|");
    const row = grouped.get(key) ?? {
      key,
      terms: [],
      targets,
      sources: [],
      ambiguous: new Set(targets.map((t) => t.label.toLowerCase())).size > 1,
    };
    row.terms.push(entry.term);
    row.sources = unique([...row.sources, ...entry.sources]);
    grouped.set(key, row);
  }
  const kindOrder: UnderstandingKind[] = ["Measure", "Metric", "Dimension", "Attribute", "Value filter", "Value", "Not available"];
  const understanding = [...grouped.values()]
    .map((row) => ({ ...row, terms: unique(row.terms).sort((a, b) => a.localeCompare(b)) }))
    .sort((a, b) => {
      const ka = kindOrder.indexOf(a.targets[0]?.kind ?? "Value");
      const kb = kindOrder.indexOf(b.targets[0]?.kind ?? "Value");
      return ka - kb || (a.targets[0]?.label ?? "").localeCompare(b.targets[0]?.label ?? "");
    });

  // ---- coverage -----------------------------------------------------------
  const gaps: CoverageGap[] = [];
  let covered = 0;
  let total = 0;
  const check = (label: string, kind: CoverageGap["kind"], governed: boolean, aliasCount: number) => {
    total += 1;
    const missing: string[] = [];
    if (!governed) missing.push("business definition");
    if (aliasCount === 0) missing.push("business alias");
    if (missing.length) gaps.push({ label, kind, missing });
    else covered += 1;
  };
  for (const measure of measureEntries) check(measure.name, "Measure", measure.definitionGoverned, measure.synonyms.length);
  for (const dimension of dimensions) {
    if (!dimension.synthetic) check(dimension.name, "Dimension", dimension.definitionGoverned, dimension.aliases.length);
    for (const attr of dimension.attributes) {
      if (attr.aiResolvable) check(attr.name, "Attribute", attr.definitionGoverned, attr.synonyms.length + attr.values.filter((v) => v.aliases.length).length);
    }
  }
  const valueSynonyms = understanding.filter((row) => row.targets.every((t) => t.kind === "Value")).reduce((sum, row) => sum + row.terms.length, 0);
  const conceptAliases = understanding.filter((row) => !row.targets.every((t) => t.kind === "Value")).reduce((sum, row) => sum + row.terms.length, 0);

  const coverage: CoverageSummary = {
    measures: measureEntries.length,
    derivedMetrics: derived.filter((item) => item.available).length,
    dimensions: dimensions.filter((d) => !d.synthetic).length,
    attributes: dimensions.reduce((sum, d) => sum + d.attributes.length, 0),
    relationships: measureEntries.reduce((sum, m) => sum + m.dimensionIds.length, 0),
    joins: model.relationships.length,
    businessTerms: Object.keys(pack.glossary.terms).length,
    aliases: conceptAliases,
    valueSynonyms,
    aiCoverage: total ? Math.round((covered / total) * 100) : 0,
    coveredConcepts: covered,
    totalConcepts: total,
    gaps,
  };

  const rules = (key: string) =>
    unique([...(model.domainRules?.[key] ?? []), ...(pack.glossary.domainRules?.[key] ?? [])]);

  return {
    domain: model.domain,
    version: model.version,
    measures: measureEntries,
    derived,
    dimensions,
    understanding,
    coverage,
    hierarchies: hierarchies.map((h) => ({ name: h.name, levels: h.levels.map(levelLabel) })),
    rules: { always: rules("always_rules"), never: rules("never_rules") },
  };
}

// ---- search -----------------------------------------------------------------

export type SearchKind = "Measure" | "Metric" | "Dimension" | "Attribute" | "Value" | "Business term";

export interface SearchHit {
  key: string;
  kind: SearchKind;
  label: string;
  context: string;
  score: number;
  section: "measures" | "dimensions" | "ai";
  targetId: string;
}

interface Field {
  text: string;
  weight: number;
  reason: string;
  exact?: boolean;
}

function scoreFields(needle: string, fields: Field[]): { score: number; reason: string } | null {
  let best: { score: number; reason: string } | null = null;
  for (const field of fields) {
    const text = field.text.toLowerCase();
    if (!text.includes(needle)) continue;
    const pattern = escapeRegExp(needle);
    let score: number;
    if (text === needle) score = field.weight + 25;
    else if (new RegExp(`\\b${pattern}\\b`).test(text)) score = field.weight + 10;
    else if (new RegExp(`\\b${pattern}`).test(text)) score = Math.round(field.weight * 0.5);
    else score = Math.round(field.weight * 0.3);
    if (!best || score > best.score) best = { score, reason: field.reason.replace("{text}", field.text) };
  }
  return best;
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function searchSemanticLayer(layer: BusinessSemanticLayer, query: string, limit = 14): SearchHit[] {
  const needle = query.trim().toLowerCase();
  if (needle.length < 2) return [];
  const hits = new Map<string, SearchHit>();
  const add = (hit: SearchHit) => {
    const existing = hits.get(hit.key);
    if (!existing || existing.score < hit.score) hits.set(hit.key, hit);
  };

  for (const measure of layer.measures) {
    const match = scoreFields(needle, [
      { text: measure.name, weight: 100, reason: "Measure name" },
      ...measure.synonyms.map((s) => ({ text: s, weight: 85, reason: `Alias “{text}”` })),
      { text: measure.definition, weight: 60, reason: "Business definition" },
      { text: measure.businessFormula, weight: 40, reason: "Formula" },
      ...measure.examples.map((e) => ({ text: e.text, weight: 25, reason: `Example “{text}”` })),
    ]);
    if (match) add({ key: `m:${measure.id}`, kind: "Measure", label: measure.name, context: match.reason, score: match.score, section: "measures", targetId: measure.id });
  }
  const measureHits = new Set([...hits.values()].filter((hit) => hit.score >= 80).map((hit) => hit.targetId));
  for (const metric of layer.derived) {
    const match = scoreFields(needle, [
      { text: metric.name, weight: 95, reason: "Metric name" },
      ...metric.synonyms.map((s) => ({ text: s, weight: 80, reason: `Alias “{text}”` })),
      { text: metric.definition, weight: 45, reason: "Metric definition" },
      ...metric.rules.map((r) => ({ text: r, weight: 30, reason: "Calculation rule" })),
    ]);
    if (match) {
      add({ key: `d:${metric.id}`, kind: "Metric", label: metric.name, context: match.reason, score: match.score, section: "measures", targetId: metric.id });
      continue;
    }
    const related = metric.appliesTo.filter((id) => measureHits.has(id));
    if (related.length) {
      const names = related.map((id) => layer.measures.find((m) => m.id === id)?.name).filter(Boolean);
      add({
        key: `d:${metric.id}`,
        kind: "Metric",
        label: metric.name,
        context: `Related: applies to ${names.slice(0, 3).join(", ")}`,
        score: 48,
        section: "measures",
        targetId: metric.id,
      });
    }
  }
  for (const dimension of layer.dimensions) {
    const match = scoreFields(needle, [
      { text: dimension.name, weight: 95, reason: "Dimension name" },
      ...dimension.aliases.map((s) => ({ text: s, weight: 65, reason: `Alias “{text}”` })),
      { text: dimension.definition, weight: 40, reason: "Business definition" },
    ]);
    if (match) add({ key: `dim:${dimension.id}`, kind: "Dimension", label: dimension.name, context: match.reason, score: match.score, section: "dimensions", targetId: dimension.id });
    for (const attr of dimension.attributes) {
      const attrMatch = scoreFields(needle, [
        { text: attr.name, weight: 90, reason: `${dimension.name} attribute` },
        ...attr.synonyms.map((s) => ({ text: s, weight: 82, reason: `Alias “{text}”` })),
        { text: attr.description, weight: 35, reason: "Attribute definition" },
      ]);
      if (attrMatch) {
        add({ key: `a:${attr.id}`, kind: "Attribute", label: attr.name, context: attrMatch.reason, score: attrMatch.score, section: "dimensions", targetId: dimension.id });
      }
      for (const value of attr.values) {
        const valueMatch = scoreFields(needle, [
          { text: value.value, weight: 70, reason: `${attr.name} value` },
          ...value.aliases.map((s) => ({ text: s, weight: 60, reason: `“{text}” means ${value.value}` })),
        ]);
        if (valueMatch) {
          add({ key: `v:${attr.id}:${value.value}`, kind: "Value", label: value.value, context: valueMatch.reason, score: valueMatch.score, section: "dimensions", targetId: dimension.id });
        }
      }
    }
  }
  const found = new Set([...hits.values()].map((hit) => hit.label.toLowerCase()));
  for (const row of layer.understanding) {
    if (row.targets.every((t) => t.kind === "Value")) continue;
    if (row.targets.every((t) => found.has(t.label.toLowerCase()))) continue;
    const term = row.terms.find((t) => t.toLowerCase().includes(needle));
    if (!term) continue;
    const exact = term.toLowerCase() === needle;
    add({
      key: `t:${row.key}`,
      kind: "Business term",
      label: term,
      context: `AI understands as ${row.targets.map((t) => t.label).join(" or ")}`,
      score: exact ? 75 : 50,
      section: "ai",
      targetId: row.key,
    });
  }
  return [...hits.values()]
    .filter((hit) => hit.score >= 25)
    .sort((a, b) => b.score - a.score || a.label.localeCompare(b.label))
    .slice(0, limit);
}
