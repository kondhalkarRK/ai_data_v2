"use client";

import { Search } from "lucide-react";
import * as React from "react";

import { LoadingState } from "@/components/loading/loading-state";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useSemanticPack } from "@/hooks/use-semantic";

export default function GlossaryPage() {
  const pack = useSemanticPack();
  const [query, setQuery] = React.useState("");

  const terms = React.useMemo(() => {
    if (!pack.data) return [];
    const needle = query.trim().toLowerCase();
    return Object.entries(pack.data.glossary.terms).filter(([name, term]) => {
      if (!needle) return true;
      return [name, term.definition, term.category, ...term.synonyms]
        .join(" ")
        .toLowerCase()
        .includes(needle);
    });
  }, [pack.data, query]);

  return (
    <>
      <PageHeader
        title="Business Glossary"
        description="Canonical business language mapped to governed measures and dimensions."
      />
      <div className="relative mb-4 max-w-lg">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="pl-9"
          placeholder="Search terms and synonyms"
          aria-label="Search glossary"
        />
      </div>

      {pack.isPending ? (
        <LoadingState size="sm" title="Loading glossary" />
      ) : pack.isError ? (
        <p className="text-sm text-danger">The glossary is unavailable.</p>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {terms.map(([name, term]) => (
            <Card key={name}>
              <CardContent className="pt-5">
                <div className="flex items-start justify-between gap-3">
                  <CardTitle className="text-base">{term.displayLabel ?? name}</CardTitle>
                  <span className="rounded-full border border-border px-2 py-0.5 text-2xs text-muted-foreground">
                    {term.category}
                  </span>
                </div>
                <CardDescription className="mt-2 leading-relaxed">
                  {term.definition}
                </CardDescription>
                {term.synonyms.length ? (
                  <div className="mt-3 flex flex-wrap gap-1">
                    {term.synonyms.map((synonym) => (
                      <span
                        key={synonym}
                        className="rounded-full bg-surface-sunken px-2 py-0.5 text-2xs"
                      >
                        {synonym}
                      </span>
                    ))}
                  </div>
                ) : null}
                {term.mapsToMeasure || term.mapsToDimension ? (
                  <p className="mt-3 font-mono text-2xs text-primary">
                    → {term.mapsToMeasure ?? term.mapsToDimension}
                  </p>
                ) : null}
              </CardContent>
            </Card>
          ))}
          {!terms.length ? (
            <p className="text-sm text-muted-foreground">
              No glossary terms match “{query}”.
            </p>
          ) : null}
        </div>
      )}
    </>
  );
}
