"use client";

import { BookOpen, Network, Star, X } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

import { useSemanticPack } from "@/hooks/use-semantic";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui-store";

interface PaletteItem {
  id: string;
  label: string;
  hint: string;
  group: "Glossary" | "Semantic Graph" | "Saved insights";
  href?: string;
}

export function CommandPalette() {
  const open = useUiStore((state) => state.commandPaletteOpen);
  const setOpen = useUiStore((state) => state.setCommandPaletteOpen);
  const router = useRouter();
  const pack = useSemanticPack();
  const [query, setQuery] = React.useState("");
  const [saved, setSaved] = React.useState<Array<{ id: string; title: string; question: string }>>(
    [],
  );
  const inputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen(!open);
      }
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, setOpen]);

  React.useEffect(() => {
    if (!open) return;
    setQuery("");
    inputRef.current?.focus();
    void apiClient
      .get<Array<{ id: string; title: string; question: string }>>("/api/v1/questions")
      .then(setSaved)
      .catch(() => setSaved([]));
  }, [open]);

  const items = React.useMemo(() => {
    const glossary: PaletteItem[] = Object.entries(pack.data?.glossary.terms ?? {})
      .slice(0, 40)
      .map(([name, term]) => ({
        id: `glossary-${name}`,
        label: term.displayLabel || name,
        hint: term.definition.slice(0, 80),
        group: "Glossary",
        href: `/semantic?tab=glossary&q=${encodeURIComponent(name)}`,
      }));

    const graph: PaletteItem[] = [
      {
        id: "graph-analytics",
        label: "Analytics Builder",
        hint: "No-code business metrics, dimensions, and charts",
        group: "Semantic Graph",
        href: "/analytics-builder",
      },
      {
        id: "graph-ontology",
        label: "Open Semantic Galaxy",
        hint: "Jump to the ontology knowledge graph",
        group: "Semantic Graph",
        href: "/semantic?tab=graph",
      },
      {
        id: "graph-models",
        label: "Semantic models",
        hint: "Browse tables, measures, and dimensions",
        group: "Semantic Graph",
        href: "/semantic?tab=model",
      },
    ];

    const insights: PaletteItem[] = saved.map((row) => ({
      id: `saved-${row.id}`,
      label: row.title,
      hint: row.question,
      group: "Saved insights",
      href: `/chat?q=${encodeURIComponent(row.question)}`,
    }));

    const q = query.trim().toLowerCase();
    return [...glossary, ...graph, ...insights].filter((item) => {
      if (!q) return true;
      return (
        item.label.toLowerCase().includes(q) ||
        item.hint.toLowerCase().includes(q) ||
        item.group.toLowerCase().includes(q)
      );
    });
  }, [pack.data, saved, query]);

  if (!open) return null;

  const grouped = items.reduce<Record<string, PaletteItem[]>>((acc, item) => {
    acc[item.group] = [...(acc[item.group] ?? []), item];
    return acc;
  }, {});

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/35 p-4 pt-[12vh] backdrop-blur-[2px]">
      <button
        type="button"
        className="absolute inset-0 cursor-default"
        aria-label="Close command palette"
        onClick={() => setOpen(false)}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="relative z-10 w-full max-w-lg overflow-hidden rounded-2xl border border-border bg-background shadow-2xl"
      >
        <div className="flex items-center gap-2 border-b border-border px-3">
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Jump to glossary, graph, or saved insight…"
            className="h-12 flex-1 bg-transparent text-sm outline-none"
            aria-label="Command search"
          />
          <button
            type="button"
            className="rounded-md p-1 text-muted-foreground hover:bg-muted"
            onClick={() => setOpen(false)}
            aria-label="Close"
          >
            <X className="size-4" />
          </button>
        </div>
        <div className="max-h-[50vh] overflow-auto p-2">
          {Object.keys(grouped).length === 0 ? (
            <p className="px-2 py-6 text-center text-sm text-muted-foreground">No matches.</p>
          ) : (
            Object.entries(grouped).map(([group, groupItems]) => (
              <div key={group} className="mb-2">
                <p className="px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                  {group}
                </p>
                <ul>
                  {groupItems.slice(0, 8).map((item) => {
                    const Icon =
                      item.group === "Glossary"
                        ? BookOpen
                        : item.group === "Semantic Graph"
                          ? Network
                          : Star;
                    return (
                      <li key={item.id}>
                        <button
                          type="button"
                          className={cn(
                            "flex w-full items-start gap-2 rounded-xl px-2 py-2 text-left text-sm hover:bg-muted/70",
                          )}
                          onClick={() => {
                            if (item.href) router.push(item.href);
                            setOpen(false);
                          }}
                        >
                          <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                          <span className="min-w-0">
                            <span className="block truncate font-medium">{item.label}</span>
                            <span className="block truncate text-xs text-muted-foreground">
                              {item.hint}
                            </span>
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))
          )}
        </div>
        <p className="border-t border-border px-3 py-2 text-[11px] text-muted-foreground">
          Tip: press Ctrl/Cmd+K anytime
        </p>
      </div>
    </div>
  );
}
