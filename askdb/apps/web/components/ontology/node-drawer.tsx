"use client";

import type { OntologyNode, OntologySnapshot } from "@nql/shared-types";
import { AnimatePresence, motion } from "framer-motion";
import { BadgeCheck, KeyRound, ShieldAlert, Sparkles, Star, X } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  deriveAssetContext,
  storyVerb,
  type ContextOverlay,
} from "@/lib/ontology/asset-context";
import { cn } from "@/lib/utils";

type Tab = "overview" | "schema" | "reach" | "lineage";

const TABS: ReadonlyArray<{ id: Tab; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "schema", label: "Schema" },
  { id: "reach", label: "Reach" },
  { id: "lineage", label: "Lineage" },
];

const EMPTY_SNAPSHOT: OntologySnapshot = {
  nodes: [],
  edges: [],
  clusters: [],
  metadata: {
    industry: "automotive",
    version: "1",
    compiledAt: new Date().toISOString(),
    nodeCount: 0,
    edgeCount: 0,
    buildMs: 0,
  },
};

export function NodeDrawer({
  node,
  snapshot,
  overlay = "business",
  onClose,
  onFocus,
}: {
  node: OntologyNode | null;
  snapshot?: OntologySnapshot | null;
  overlay?: ContextOverlay;
  onClose: () => void;
  onFocus?: (id: string) => void;
}) {
  return (
    <AnimatePresence>
      {node ? (
        <DrawerContent
          key={node.id}
          node={node}
          snapshot={snapshot ?? EMPTY_SNAPSHOT}
          overlay={overlay}
          onClose={onClose}
          onFocus={onFocus}
        />
      ) : null}
    </AnimatePresence>
  );
}

function DrawerContent({
  node,
  snapshot,
  overlay,
  onClose,
  onFocus,
}: {
  node: OntologyNode;
  snapshot: OntologySnapshot;
  overlay: ContextOverlay;
  onClose: () => void;
  onFocus?: (id: string) => void;
}) {
  const [tab, setTab] = React.useState<Tab>("overview");
  const context = deriveAssetContext(node, snapshot);

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
      className="absolute inset-y-0 right-0 z-20 flex w-full max-w-[31rem] flex-col border-l border-border/60 bg-surface-raised/90 shadow-[var(--shadow-overlay)] backdrop-blur-xl"
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
            <div className="mt-2 flex flex-wrap gap-1">
              {context.badges.includes("certified") ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-success/15 px-2 py-0.5 text-[10px] font-medium">
                  <BadgeCheck className="size-3" /> Certified
                </span>
              ) : null}
              {context.badges.includes("trusted") ? (
                <span className="rounded-full bg-info/15 px-2 py-0.5 text-[10px] font-medium">
                  Trusted
                </span>
              ) : null}
              {context.badges.includes("popular") ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[10px]">
                  <Star className="size-3" /> Popular
                </span>
              ) : null}
              {context.badges.includes("review") ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-warning/20 px-2 py-0.5 text-[10px]">
                  <ShieldAlert className="size-3" /> Review required
                </span>
              ) : null}
            </div>
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
        {tab === "overview" ? (
          <Overview
            node={node}
            overlay={overlay}
            context={context}
            snapshot={snapshot}
            onFocus={onFocus}
          />
        ) : null}
        {tab === "schema" ? <Schema node={node} /> : null}
        {tab === "reach" ? <Reach node={node} /> : null}
        {tab === "lineage" ? <Lineage node={node} snapshot={snapshot} /> : null}
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

function Overview({
  node,
  overlay,
  context,
  snapshot,
  onFocus,
}: {
  node: OntologyNode;
  overlay: ContextOverlay;
  context: ReturnType<typeof deriveAssetContext>;
  snapshot: OntologySnapshot;
  onFocus?: (id: string) => void;
}) {
  const neighbors = snapshot.edges.filter((edge) => edge.source === node.id || edge.target === node.id);

  return (
    <>
      <p className="text-[11px] text-muted-foreground">
        Business name · {node.label}
        {overlay !== "business" ? ` · Technical ${node.physicalName ?? node.id}` : ""}
      </p>
      {node.description ? (
        <p className="mt-2 text-sm leading-relaxed text-foreground">{node.description}</p>
      ) : (
        <p className="mt-2 text-sm text-muted-foreground">No business definition on this asset yet.</p>
      )}

      <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
        <Stat label="Quality" value={`${context.qualityScore}`} />
        <Stat label="Popularity" value={`${context.popularityScore}`} />
        <Stat label="Owner" value={context.owner} />
        <Stat
          label="Updated"
          value={
            context.lastUpdated
              ? new Date(context.lastUpdated).toLocaleDateString()
              : "—"
          }
        />
      </div>

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

      {neighbors.length ? (
        <>
          <SectionLabel>Relationship story</SectionLabel>
          <ol className="space-y-1.5 text-sm">
            {neighbors.slice(0, 6).map((edge) => {
              const otherId = edge.source === node.id ? edge.target : edge.source;
              const other = snapshot.nodes.find((item) => item.id === otherId);
              return (
                <li key={edge.id} className="rounded-lg border border-border/60 px-3 py-2">
                  <p className="font-medium">{node.label}</p>
                  <p className="text-[11px] text-muted-foreground">→ {storyVerb(edge)}</p>
                  <button
                    type="button"
                    className="text-primary hover:underline"
                    onClick={() => other && onFocus?.(other.id)}
                  >
                    {other?.label ?? otherId}
                  </button>
                </li>
              );
            })}
          </ol>
        </>
      ) : null}

      {context.relatedMetrics.length ? (
        <>
          <SectionLabel>Related metrics</SectionLabel>
          <div className="flex flex-wrap gap-1.5">
            {context.relatedMetrics.map((item) => (
              <button
                key={item.id}
                type="button"
                className="rounded-full bg-info/12 px-2 py-0.5 text-[11px]"
                onClick={() => onFocus?.(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </>
      ) : null}

      {context.sampleQueries.length ? (
        <>
          <SectionLabel>Sample queries</SectionLabel>
          <ul className="space-y-1 text-xs text-muted-foreground">
            {context.sampleQueries.map((item) => (
              <li key={item} className="flex items-start gap-1.5">
                <Sparkles className="mt-0.5 size-3 text-info" />
                {item}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border/60 bg-muted/20 px-2.5 py-2">
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-0.5 truncate font-medium">{value}</p>
    </div>
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

function Lineage({ node, snapshot }: { node: OntologyNode; snapshot: OntologySnapshot }) {
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
      {snapshot.edges.length ? (
        <p className="mt-4 text-[11px] text-muted-foreground">
          {snapshot.edges.filter((edge) => edge.source === node.id || edge.target === node.id).length}{" "}
          live graph connections.
        </p>
      ) : null}
    </>
  );
}
