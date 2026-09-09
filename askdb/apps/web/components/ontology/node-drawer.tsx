"use client";

import type { OntologyNode } from "@nql/shared-types";
import { AnimatePresence, motion } from "framer-motion";
import { KeyRound, X } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Tab = "overview" | "schema" | "reach" | "lineage";

const TABS: ReadonlyArray<{ id: Tab; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "schema", label: "Schema" },
  { id: "reach", label: "Reach" },
  { id: "lineage", label: "Lineage" },
];

export function NodeDrawer({
  node,
  onClose,
}: {
  node: OntologyNode | null;
  onClose: () => void;
}) {
  return (
    <AnimatePresence>
      {node ? <DrawerContent key={node.id} node={node} onClose={onClose} /> : null}
    </AnimatePresence>
  );
}

function DrawerContent({
  node,
  onClose,
}: {
  node: OntologyNode;
  onClose: () => void;
}) {
  const [tab, setTab] = React.useState<Tab>("overview");

  React.useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <motion.aside
      aria-label={`${node.label} details`}
      className="absolute inset-y-0 right-0 z-20 flex w-full max-w-[31rem] flex-col border-l border-border bg-surface-raised shadow-[var(--shadow-overlay)]"
      // Content is present on the first paint. The requirement is an immediate drawer,
      // so entrance animation must never delay visibility or accessibility.
      initial={false}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 32, opacity: 0 }}
      transition={{ duration: 0.16, ease: "easeOut" }}
    >
      <header className="border-b border-border px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p
              className="mb-2 flex items-center gap-2 text-2xs font-semibold uppercase tracking-[0.14em]"
              style={{ color: node.clusterColor }}
            >
              <span
                className="size-2 rounded-full"
                style={{ backgroundColor: node.clusterColor }}
                aria-hidden="true"
              />
              {node.cluster}
            </p>
            <h2 className="truncate text-2xl font-semibold tracking-tight">{node.label}</h2>
            <p className="mt-1 font-mono text-xs text-muted-foreground">{node.id}</p>
          </div>
          <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close details">
            <X />
          </Button>
        </div>
      </header>

      <div
        role="tablist"
        aria-label="Node details"
        className="grid grid-cols-4 border-b border-border px-3"
      >
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            onClick={() => setTab(item.id)}
            className={cn(
              "border-b-2 px-2 py-3 text-sm transition-colors",
              tab === item.id
                ? "border-primary font-medium text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4">
        {tab === "overview" ? <Overview node={node} /> : null}
        {tab === "schema" ? <Schema node={node} /> : null}
        {tab === "reach" ? <Reach node={node} /> : null}
        {tab === "lineage" ? <Lineage node={node} /> : null}
      </div>

      <footer className="grid grid-cols-4 border-t border-border px-2 py-2 text-center text-xs text-muted-foreground">
        <span>Contracts</span>
        <span>Docs</span>
        <span>Memory</span>
        <span>Flow</span>
      </footer>
    </motion.aside>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="mb-2 mt-5 text-2xs font-semibold uppercase tracking-[0.13em] text-muted-foreground first:mt-0">
      {children}
    </h3>
  );
}

function Overview({ node }: { node: OntologyNode }) {
  return (
    <>
      {node.description ? (
        <p className="text-sm leading-relaxed text-foreground">{node.description}</p>
      ) : null}
      <SectionLabel>Synonyms</SectionLabel>
      {node.synonyms.length ? (
        <div className="flex flex-wrap gap-1.5">
          {node.synonyms.map((synonym) => (
            <span
              key={synonym}
              className="rounded-full border border-border bg-surface-sunken px-2.5 py-1 text-xs"
            >
              {synonym}
            </span>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">None in the glossary.</p>
      )}
      <SectionLabel>Source bindings</SectionLabel>
      <dl className="divide-y divide-border rounded-[var(--radius-control)] border border-border text-sm">
        <div className="grid grid-cols-[6rem_1fr] gap-3 px-3 py-2.5">
          <dt className="font-medium">Semantic</dt>
          <dd className="break-all font-mono text-xs text-muted-foreground">
            {node.tables.join(", ") || "—"}
          </dd>
        </div>
        <div className="grid grid-cols-[6rem_1fr] gap-3 px-3 py-2.5">
          <dt className="font-medium">Physical</dt>
          <dd className="break-all font-mono text-xs text-muted-foreground">
            {node.physicalName ?? "—"}
          </dd>
        </div>
      </dl>
      {node.grain ? (
        <>
          <SectionLabel>Grain</SectionLabel>
          <p className="text-sm">{node.grain}</p>
        </>
      ) : null}
    </>
  );
}

function Schema({ node }: { node: OntologyNode }) {
  if (!node.columns.length) {
    return <p className="text-sm text-muted-foreground">No field schema on this node.</p>;
  }
  return (
    <div className="overflow-hidden rounded-[var(--radius-control)] border border-border">
      <table className="w-full text-left text-sm">
        <thead className="bg-surface-sunken text-2xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-3 py-2 font-medium">Attribute</th>
            <th className="px-3 py-2 font-medium">Type</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {node.columns.map((column) => (
            <tr key={column.name}>
              <td className="px-3 py-2.5">
                <span className="flex items-center gap-1.5 font-mono text-xs">
                  {column.role === "key" ? (
                    <KeyRound className="size-3 text-warning" aria-label="Primary key" />
                  ) : null}
                  {column.name}
                </span>
                {column.references ? (
                  <span className="mt-1 block text-2xs text-muted-foreground">
                    ref:{column.references}
                  </span>
                ) : null}
              </td>
              <td className="px-3 py-2.5 text-xs text-muted-foreground">
                {column.references ? `ref:${column.references.split(".")[0]}` : column.type}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Reach({ node }: { node: OntologyNode }) {
  return (
    <>
      <div className="mb-4 rounded-[var(--radius-control)] bg-surface-sunken p-3">
        <p className="text-2xs uppercase tracking-wide text-muted-foreground">Graph degree</p>
        <p className="mt-1 text-2xl font-semibold">{node.degree}</p>
      </div>
      <ul className="space-y-2">
        {node.relationships.map((relationship) => (
          <li
            key={relationship}
            className="rounded-[var(--radius-control)] border border-border px-3 py-2 text-sm"
          >
            {relationship}
          </li>
        ))}
        {!node.relationships.length ? (
          <li className="text-sm text-muted-foreground">No connected edges.</li>
        ) : null}
      </ul>
    </>
  );
}

function Lineage({ node }: { node: OntologyNode }) {
  return (
    <>
      <ul className="space-y-2">
        {node.lineage.map((line) => (
          <li
            key={line}
            className="rounded-[var(--radius-control)] border border-border px-3 py-2 font-mono text-xs"
          >
            {line}
          </li>
        ))}
        {!node.lineage.length ? (
          <li className="text-sm text-muted-foreground">No lineage paths.</li>
        ) : null}
      </ul>
      {node.primaryKey ? (
        <>
          <SectionLabel>Primary key</SectionLabel>
          <code className="text-xs">{node.primaryKey}</code>
        </>
      ) : null}
    </>
  );
}
