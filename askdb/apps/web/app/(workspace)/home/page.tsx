"use client";

import Link from "next/link";

import { ConnectedDataSources } from "@/components/home/connected-data-sources";
import { HeroBackdrop } from "@/components/home/hero-backdrop";
import { HeroLiveDemo } from "@/components/home/hero-live-demo";
import { BrandWordmark } from "@/components/brand/wordmark";
import { Button } from "@/components/ui/button";
import { PageShell } from "@/components/ui/page-shell";

const FEATURE_CHIPS = [
  "Semantic Layer Grounded",
  "Zero-Guess SQL",
  "Works With Any Warehouse",
  "Built-in Data Quality",
  "Row-Level Governance",
] as const;

export default function HomePage() {
  return (
    <PageShell className="max-w-6xl">
      <section className="relative overflow-hidden rounded-[var(--radius-card)] border border-border/50 bg-card/40 shadow-[var(--shadow-card)]">
        <HeroBackdrop />
        <div className="relative grid gap-8 px-5 py-10 sm:px-8 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] lg:items-center lg:gap-10 lg:px-10 lg:py-14">
          <div>
            <BrandWordmark size="hero" withPeriod />
            <p className="mt-5 max-w-xl text-base leading-relaxed text-muted-foreground sm:text-lg">
              Ask your data anything, in plain English. Every answer is grounded in your
              semantic layer, validated against your data quality — no guesswork, no wrong
              numbers.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Button asChild size="lg">
                <Link href="/chat">Ask your data a question</Link>
              </Button>
              <Button asChild size="lg" variant="secondary">
                <a href="#how-it-works">See how it works</a>
              </Button>
            </div>
            <ul className="mt-8 flex flex-wrap gap-2">
              {FEATURE_CHIPS.map((chip) => (
                <li
                  key={chip}
                  className="rounded-full border border-border/70 bg-background/70 px-2.5 py-1 text-[11px] text-muted-foreground backdrop-blur-sm"
                >
                  {chip}
                </li>
              ))}
            </ul>
          </div>
          <HeroLiveDemo />
        </div>
      </section>

      <div className="mt-10 border-t border-border/60 pt-8">
        <ConnectedDataSources />
      </div>
    </PageShell>
  );
}
