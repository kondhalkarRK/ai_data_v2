"use client";

import { BookOpenText, Boxes, Network } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { LoadingState } from "@/components/loading/loading-state";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { useSemanticPack } from "@/hooks/use-semantic";
import { cn } from "@/lib/utils";

const TABS = [
  {
    id: "ontology",
    title: "Ontology Browser",
    description:
      "Business entities, relationships, synonyms and source bindings as a queryable graph.",
    detail:
      "Includes unified search across entities, measures, dimensions and glossary synonyms.",
    href: "/semantic/ontology",
    icon: Network,
  },
  {
    id: "model",
    title: "Semantic Model",
    description:
      "Governed tables, field-level schema, grains, keys and join contracts with cardinality.",
    detail: "Data products and join paths live here — cardinality badges on every relationship.",
    href: "/semantic/models",
    icon: Boxes,
  },
  {
    id: "glossary",
    title: "Business Glossary",
    description:
      "Canonical terms, synonyms, calculation rules and disambiguation guidance.",
    detail: "Card layout grouped by business category.",
    href: "/semantic/glossary",
    icon: BookOpenText,
  },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function SemanticPage() {
  const pack = useSemanticPack();
  const [active, setActive] = useState<TabId>("ontology");
  const current = TABS.find((tab) => tab.id === active) ?? TABS[0];
  const Icon = current.icon;

  return (
    <>
      <PageHeader
        title="Semantic Atlas"
        description="The governed knowledge layer behind every generated query — ontology, model contracts, and glossary."
      />

      {pack.isPending ? (
        <LoadingState title="Loading semantic pack" size="sm" />
      ) : pack.isError ? (
        <Card>
          <CardContent className="pt-5 text-sm text-danger">
            The active semantic pack could not be loaded. Its YAML may be missing or
            invalid.
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="mb-5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="rounded-full border border-border bg-surface-raised px-2.5 py-1 font-medium text-foreground">
              {pack.data.summary.label}
            </span>
            <span>{pack.data.summary.tableCount} tables</span>
            <span aria-hidden="true">·</span>
            <span>{pack.data.summary.measureCount} measures</span>
            <span aria-hidden="true">·</span>
            <span>{pack.data.summary.glossaryTermCount} glossary terms</span>
            <span aria-hidden="true">·</span>
            <span>v{pack.data.summary.version}</span>
          </div>

          <div className="mb-4 inline-flex w-full max-w-2xl rounded-[var(--radius-control)] border border-border bg-muted/30 p-0.5 text-sm">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={cn(
                  "flex-1 rounded-[var(--radius-control)] px-3 py-2 text-center",
                  active === tab.id
                    ? "bg-background font-medium text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
                )}
                onClick={() => setActive(tab.id)}
              >
                {tab.title}
              </button>
            ))}
          </div>

          <Link href={current.href} className="group block rounded-[var(--radius-card)]">
            <Card className="transition-[border-color,box-shadow,transform] duration-150 group-hover:-translate-y-0.5 group-hover:border-primary/30 group-hover:shadow-[var(--shadow-raised)]">
              <CardContent className="flex gap-4 pt-5">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-[var(--radius-control)] bg-primary/10 text-primary">
                  <Icon className="size-4" aria-hidden="true" />
                </span>
                <div>
                  <CardTitle className="text-base">{current.title}</CardTitle>
                  <CardDescription className="mt-1 leading-relaxed">
                    {current.description}
                  </CardDescription>
                  <p className="mt-3 text-xs text-muted-foreground">{current.detail}</p>
                  <p className="mt-4 text-sm font-medium text-primary">Open {current.title} →</p>
                </div>
              </CardContent>
            </Card>
          </Link>

          <p className="mt-4 text-xs text-muted-foreground">
            Former Join Paths, Data Products, and Unified Search capabilities map into these
            three tabs (model relationships/tables and ontology search).
          </p>
        </>
      )}
    </>
  );
}
