"use client";

import { ConnectedDataSources } from "@/components/home/connected-data-sources";
import { HomeStory } from "@/components/home/home-story";

export default function HomePage() {
  return (
    <div className="w-full min-w-0 space-y-8 pb-8">
      <HomeStory />
      <section className="grid gap-3 sm:grid-cols-3" aria-label="How Ask Me works">
        {[["01", "Ask", "Start with a business question in plain language."], ["02", "Understand", "Use governed definitions and inspect the evidence behind an answer."], ["03", "Act", "Explore an executive view or build a report for the next conversation."]].map(([step, title, description]) => <div key={step} className="rounded-2xl border border-border bg-surface-raised p-5"><span className="text-xs font-semibold tracking-widest text-primary">{step}</span><h2 className="mt-2 text-base font-semibold">{title}</h2><p className="mt-1 text-sm leading-relaxed text-muted-foreground">{description}</p></div>)}
      </section>
      <div className="rounded-2xl border border-border bg-surface-raised p-5 sm:p-6"><ConnectedDataSources /></div>
    </div>
  );
}
