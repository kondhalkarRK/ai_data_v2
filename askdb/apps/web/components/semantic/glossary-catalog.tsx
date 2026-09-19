"use client";

import type { GlossaryTerm, SemanticPackResponse } from "@nql/shared-types";
import { BookOpenText, Link2, Search, Sparkles, Table2 } from "lucide-react";
import * as React from "react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type TermEntry = [string, GlossaryTerm];

function relatedTable(pack: SemanticPackResponse, term: GlossaryTerm): string | null {
  if (term.mapsToMeasure) {
    return pack.model.measures[term.mapsToMeasure]?.sourceTable ?? term.mapsToMeasure;
  }
  if (term.mapsToDimension) {
    return pack.model.dimensions[term.mapsToDimension]?.sourceTable ?? term.mapsToDimension;
  }
  return null;
}

export function GlossaryCatalog({
  pack,
  initialQuery = "",
}: {
  pack: SemanticPackResponse;
  initialQuery?: string;
}) {
  const [query, setQuery] = React.useState(initialQuery);
  const [category, setCategory] = React.useState<string>("all");
  const [kind, setKind] = React.useState<"all" | "measure" | "dimension" | "other">("all");
  const [selectedId, setSelectedId] = React.useState<string | null>(null);

  const allTerms = React.useMemo(() => Object.entries(pack.glossary.terms), [pack.glossary.terms]);

  const categories = React.useMemo(() => {
    const counts = new Map<string, number>();
    for (const [, term] of allTerms) {
      const key = term.category?.trim() || "General";
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [allTerms]);

  const filtered = React.useMemo(() => {
    const needle = query.trim().toLowerCase();
    return allTerms.filter(([name, term]) => {
      const cat = term.category?.trim() || "General";
      if (category !== "all" && cat !== category) return false;
      if (kind === "measure" && !term.mapsToMeasure) return false;
      if (kind === "dimension" && !term.mapsToDimension) return false;
      if (kind === "other" && (term.mapsToMeasure || term.mapsToDimension)) return false;
      if (!needle) return true;
      return [name, term.displayLabel, term.definition, term.category, ...term.synonyms]
        .join(" ")
        .toLowerCase()
        .includes(needle);
    });
  }, [allTerms, category, kind, query]);

  React.useEffect(() => {
    if (!filtered.length) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !filtered.some(([id]) => id === selectedId)) {
      setSelectedId(filtered[0]![0]);
    }
  }, [filtered, selectedId]);

  const selected = filtered.find(([id]) => id === selectedId) ?? filtered[0] ?? null;

  return (
    <div className="grid min-h-[560px] overflow-hidden rounded-2xl border border-border/70 bg-surface-raised/80 lg:grid-cols-[200px_minmax(0,1fr)_300px]">
      <aside className="border-b border-border/60 p-3 lg:border-b-0 lg:border-r">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Domains
        </p>
        <nav className="space-y-0.5">
          <CategoryButton
            label="All terms"
            count={allTerms.length}
            active={category === "all"}
            onClick={() => setCategory("all")}
          />
          {categories.map(([name, count]) => (
            <CategoryButton
              key={name}
              label={name}
              count={count}
              active={category === name}
              onClick={() => setCategory(name)}
            />
          ))}
        </nav>
      </aside>

      <section className="flex min-h-0 flex-col border-b border-border/60 p-3 lg:border-b-0 lg:border-r">
        <div className="relative mb-2">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="h-9 pl-8 text-sm"
            placeholder="Search terms, synonyms, definitions"
            aria-label="Search glossary"
          />
        </div>
        <div className="mb-3 flex flex-wrap gap-1">
          {(
            [
              ["all", "All"],
              ["measure", "Metrics"],
              ["dimension", "Dimensions"],
              ["other", "Other"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={cn(
                "rounded-full px-2.5 py-1 text-[11px] font-medium",
                kind === id
                  ? "bg-primary/15 text-foreground"
                  : "bg-muted/40 text-muted-foreground hover:bg-muted",
              )}
              onClick={() => setKind(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
          {filtered.map(([id, term]) => (
            <button
              key={id}
              type="button"
              className={cn(
                "w-full rounded-xl border px-3 py-2.5 text-left transition-colors",
                selectedId === id
                  ? "border-primary/40 bg-primary/8"
                  : "border-border/50 bg-background/40 hover:bg-muted/40",
              )}
              onClick={() => setSelectedId(id)}
            >
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-semibold">{term.displayLabel ?? id}</p>
                <TermBadge term={term} />
              </div>
              <p className="mt-1 line-clamp-2 text-[11px] text-muted-foreground">{term.definition}</p>
            </button>
          ))}
          {!filtered.length ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No terms match this search.
            </p>
          ) : null}
        </div>
      </section>

      <aside className="min-h-0 overflow-y-auto p-4">
        {selected ? (
          <TermDetail pack={pack} id={selected[0]} term={selected[1]} />
        ) : (
          <p className="text-sm text-muted-foreground">Select a term to inspect relationships.</p>
        )}
      </aside>
    </div>
  );
}

function CategoryButton({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={cn(
        "flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left text-xs",
        active ? "bg-primary/12 font-medium text-foreground" : "text-muted-foreground hover:bg-muted/50",
      )}
      onClick={onClick}
    >
      <span className="truncate">{label}</span>
      <span className="tabular-nums text-[10px]">{count}</span>
    </button>
  );
}

function TermBadge({ term }: { term: GlossaryTerm }) {
  if (term.mapsToMeasure) {
    return (
      <span className="rounded-full bg-info/15 px-2 py-0.5 text-[10px] font-medium text-info">
        Metric
      </span>
    );
  }
  if (term.mapsToDimension) {
    return (
      <span className="rounded-full bg-success/15 px-2 py-0.5 text-[10px] font-medium">
        Dimension
      </span>
    );
  }
  return (
    <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">Term</span>
  );
}

function TermDetail({
  pack,
  id,
  term,
}: {
  pack: SemanticPackResponse;
  id: string;
  term: GlossaryTerm;
}) {
  const table = relatedTable(pack, term);
  return (
    <div className="space-y-4">
      <div>
        <div className="mb-1 flex items-center gap-2">
          <BookOpenText className="size-4 text-primary" />
          <TermBadge term={term} />
        </div>
        <h3 className="text-base font-semibold">{term.displayLabel ?? id}</h3>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{term.definition}</p>
      </div>
      {term.synonyms.length ? (
        <div>
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Synonyms
          </p>
          <div className="flex flex-wrap gap-1">
            {term.synonyms.map((item) => (
              <span key={item} className="rounded-full bg-muted/50 px-2 py-0.5 text-[11px]">
                {item}
              </span>
            ))}
          </div>
        </div>
      ) : null}
      <div className="space-y-2 text-xs">
        {term.mapsToMeasure ? (
          <p className="flex items-center gap-2">
            <Sparkles className="size-3.5 text-info" />
            <span>
              Metric <span className="font-mono text-foreground">{term.mapsToMeasure}</span>
            </span>
          </p>
        ) : null}
        {term.mapsToDimension ? (
          <p className="flex items-center gap-2">
            <Link2 className="size-3.5 text-primary" />
            <span>
              Dimension <span className="font-mono text-foreground">{term.mapsToDimension}</span>
            </span>
          </p>
        ) : null}
        {table ? (
          <p className="flex items-center gap-2">
            <Table2 className="size-3.5 text-muted-foreground" />
            <span>
              Table <span className="font-mono text-foreground">{table}</span>
            </span>
          </p>
        ) : null}
      </div>
      {term.calculationRules.length ? (
        <DetailList title="Calculation rules" items={term.calculationRules} />
      ) : null}
      {term.relatedTerms.length ? (
        <DetailList title="Related terms" items={term.relatedTerms} />
      ) : null}
      {term.exampleQuestions.length ? (
        <DetailList title="Example questions" items={term.exampleQuestions} />
      ) : null}
    </div>
  );
}

function DetailList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </p>
      <ul className="space-y-1 text-xs text-muted-foreground">
        {items.map((item) => (
          <li key={item}>• {item}</li>
        ))}
      </ul>
    </div>
  );
}
