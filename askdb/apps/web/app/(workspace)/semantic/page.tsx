"use client";

import {
  BookOpenText,
  Boxes,
  DatabaseZap,
  Network,
  Route,
  Search,
} from "lucide-react";
import Link from "next/link";

import { LoadingState } from "@/components/loading/loading-state";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { useSemanticPack } from "@/hooks/use-semantic";

const CAPABILITIES = [
  {
    title: "Ontology Browser",
    description:
      "Business entities, relationships, synonyms and source bindings as a queryable graph.",
    detail: "Force, centrality and hierarchy layouts",
    href: "/semantic/ontology",
    icon: Network,
  },
  {
    title: "Semantic Models",
    description:
      "Governed tables, field-level schema, grains, keys and relationship contracts.",
    detail: "Validated directly from semantic YAML",
    href: "/semantic/models",
    icon: Boxes,
  },
  {
    title: "Business Glossary",
    description:
      "Canonical terms, synonyms, calculation rules and disambiguation guidance.",
    detail: "Mapped to measures and dimensions",
    href: "/semantic/glossary",
    icon: BookOpenText,
  },
  {
    title: "Join Paths",
    description:
      "Inspect how facts reach dimensions and which relationship contracts are safe.",
    detail: "Cardinality and field-level join keys",
    href: "/semantic/models#relationships",
    icon: Route,
  },
  {
    title: "Data Products",
    description:
      "Discover the physical PostgreSQL objects exposed by the active industry pack.",
    detail: "Physical names and business ownership",
    href: "/semantic/models#tables",
    icon: DatabaseZap,
  },
  {
    title: "Unified Search",
    description:
      "Search across entities, measures, dimensions and glossary synonyms.",
    detail: "Available inside the ontology browser",
    href: "/semantic/ontology",
    icon: Search,
  },
] as const;

export default function SemanticPage() {
  const pack = useSemanticPack();

  return (
    <>
      <PageHeader
        title="Semantic Core"
        description="The governed knowledge layer behind every generated query."
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

          <div className="grid gap-4 md:grid-cols-2">
            {CAPABILITIES.map(({ title, description, detail, href, icon: Icon }) => (
              <Link key={title} href={href} className="group rounded-[var(--radius-card)]">
                <Card className="h-full transition-[border-color,box-shadow,transform] duration-150 group-hover:-translate-y-0.5 group-hover:border-primary/30 group-hover:shadow-[var(--shadow-raised)]">
                  <CardContent className="flex gap-4 pt-5">
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-[var(--radius-control)] bg-primary/10 text-primary">
                      <Icon className="size-4" aria-hidden="true" />
                    </span>
                    <div>
                      <CardTitle className="text-base">{title}</CardTitle>
                      <CardDescription className="mt-1 leading-relaxed">
                        {description}
                      </CardDescription>
                      <p className="mt-3 text-xs text-muted-foreground">{detail}</p>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        </>
      )}
    </>
  );
}
