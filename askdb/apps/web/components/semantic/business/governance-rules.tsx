"use client";

import { CircleCheck, CircleX } from "lucide-react";

import type { GovernanceRules as Rules } from "./semantic-layer";
import { FieldLabel } from "./ui";

export function GovernanceRules({ rules }: { rules: Rules }) {
  if (!rules.always.length && !rules.never.length) {
    return <p className="text-sm text-muted-foreground">No domain rules are declared in this pack.</p>;
  }
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <RuleList title="The AI always" items={rules.always} positive />
      <RuleList title="The AI never" items={rules.never} />
    </div>
  );
}

function RuleList({ title, items, positive = false }: { title: string; items: string[]; positive?: boolean }) {
  const Icon = positive ? CircleCheck : CircleX;
  return (
    <div className="rounded-xl border border-border/60 bg-background/50 p-3">
      <FieldLabel>
        {title} ({items.length})
      </FieldLabel>
      <ul className="space-y-1.5">
        {items.map((item) => (
          <li key={item} className="flex gap-2 text-[13px] text-foreground">
            <Icon className={positive ? "mt-0.5 size-4 shrink-0 text-success" : "mt-0.5 size-4 shrink-0 text-danger"} />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
