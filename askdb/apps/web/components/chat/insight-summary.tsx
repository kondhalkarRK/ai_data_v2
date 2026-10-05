"use client";

import { Lightbulb, Sparkles, Target } from "lucide-react";
import * as React from "react";

import type { InsightDepth, NarrationSections } from "@/components/chat/types";
import { cn } from "@/lib/utils";

export function InsightSummary({
  executive,
  analyst,
  narration,
  depth,
  onDepthChange,
  className,
}: {
  executive: string;
  analyst: string;
  narration?: NarrationSections;
  depth: InsightDepth;
  onDepthChange: (depth: InsightDepth) => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-border/70 bg-muted/25 px-4 py-3 shadow-sm",
        className,
      )}
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          AI Business Analyst
        </p>
        <div
          className="inline-flex rounded-full border border-border/70 bg-background p-0.5 text-[11px]"
          role="group"
          aria-label="Insight depth"
        >
          {(["executive", "analyst"] as const).map((option) => (
            <button
              key={option}
              type="button"
              className={cn(
                "rounded-full px-2.5 py-1 capitalize transition-colors",
                depth === option
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:text-foreground",
              )}
              aria-pressed={depth === option}
              onClick={() => onDepthChange(option)}
            >
              {option}
            </button>
          ))}
        </div>
      </div>
      {narration ? (
        <NarrationBody narration={narration} detailed={depth === "analyst"} />
      ) : (
        <p className="text-sm leading-relaxed text-foreground/90">
          {depth === "executive" ? executive : analyst}
        </p>
      )}
    </div>
  );
}

function NarrationBody({
  narration,
  detailed,
}: {
  narration: NarrationSections;
  detailed: boolean;
}) {
  const highlights = detailed ? narration.highlights : narration.highlights.slice(0, 2);
  return (
    <div className="space-y-3 text-sm leading-relaxed">
      <Section title="Executive Summary">
        <p className="text-foreground">{narration.summary}</p>
      </Section>
      {highlights.length ? (
        <Section title="Key Highlights">
          <ul className="space-y-1">
            {highlights.map((item) => (
              <li key={item} className="flex gap-2 text-foreground/90">
                <span aria-hidden="true" className="mt-2 size-1.5 shrink-0 rounded-full bg-primary/70" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      {narration.insight ? (
        <Section title="Business Insight" icon={<Lightbulb className="size-3.5" aria-hidden="true" />}>
          <p className="text-foreground/90">{narration.insight}</p>
        </Section>
      ) : null}
      {narration.focus ? (
        <Section
          title="Recommended Focus Area"
          icon={<Target className="size-3.5" aria-hidden="true" />}
        >
          <p className="text-foreground/90">{narration.focus}</p>
        </Section>
      ) : null}
      {detailed && narration.evidence?.length ? (
        <Section title="From your documents">
          {narration.evidence.map((item) => (
            <p key={item} className="text-foreground/80">
              {item}
            </p>
          ))}
        </Section>
      ) : null}
      {detailed && narration.context ? (
        <p className="text-[11px] text-muted-foreground">{narration.context}</p>
      ) : null}
    </div>
  );
}

function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h4 className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
        {icon}
        {title}
      </h4>
      {children}
    </section>
  );
}

/** One-line executive takeaway shown above the result tabs. */
export function ExecutiveTakeaway({ text, className }: { text: string; className?: string }) {
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-xl border border-primary/20 bg-primary/5 px-3 py-2.5 text-sm",
        className,
      )}
    >
      <Sparkles className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
      <p className="leading-relaxed text-foreground">{text}</p>
    </div>
  );
}
