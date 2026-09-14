"use client";

import { Check } from "lucide-react";
import * as React from "react";

import { SQLViewer } from "@/components/chat/sql-viewer";
import { CHART_SERIES } from "@/lib/design";
import { cn } from "@/lib/utils";

type DemoStage =
  | "typing"
  | "grounded"
  | "sql"
  | "quality"
  | "answer"
  | "pause";

type DemoScript = {
  domain: "Automotive" | "Insurance";
  question: string;
  sql: string;
  answerLabel: string;
  answerValue: string;
  bars: number[];
};

const SCRIPTS: DemoScript[] = [
  {
    domain: "Automotive",
    question: "Which dealer sold the most SUVs in Mumbai this quarter?",
    sql: `SELECT d.dealer_name, SUM(f.order_qty) AS units
FROM automotive.fact_sales f
JOIN automotive.dim_dealer d ON d.dealer_id = f.dealer_id
JOIN automotive.dim_carline c ON c.carline_id = f.carline_id
JOIN automotive.dim_region r ON r.region_id = f.region_id
WHERE c.car_type = 'SUV'
  AND r.city = 'Mumbai'
  AND f.sale_date >= DATE_TRUNC('quarter', CURRENT_DATE)
GROUP BY 1
ORDER BY units DESC
LIMIT 10`,
    answerLabel: "Top dealer · Mumbai SUV units",
    answerValue: "Western Motors — 184 units",
    bars: [184, 151, 128, 97, 72],
  },
  {
    domain: "Insurance",
    question: "What is the loss ratio by product this year?",
    sql: `SELECT p.product_name,
       SUM(c.incurred_amount) / NULLIF(SUM(c.earned_premium), 0) AS loss_ratio
FROM insurance.fact_claims c
JOIN insurance.dim_product p ON p.product_id = c.product_id
WHERE c.claim_date >= DATE_TRUNC('year', CURRENT_DATE)
GROUP BY 1
ORDER BY loss_ratio DESC
LIMIT 10`,
    answerLabel: "Highest loss ratio · YTD",
    answerValue: "Motor Comprehensive — 72.4%",
    bars: [72, 61, 54, 48, 41],
  },
  {
    domain: "Automotive",
    question: "Show revenue by make for sedans last month",
    sql: `SELECT c.make, SUM(f.total_sales) AS revenue
FROM automotive.fact_sales f
JOIN automotive.dim_carline c ON c.carline_id = f.carline_id
WHERE c.car_type = 'Sedan'
  AND f.sale_date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month')
  AND f.sale_date < DATE_TRUNC('month', CURRENT_DATE)
GROUP BY 1
ORDER BY revenue DESC
LIMIT 8`,
    answerLabel: "Top make · Sedan revenue",
    answerValue: "Hyundai — ₹4.2 Cr",
    bars: [92, 78, 65, 51, 44],
  },
];

const STAGE_MS: Record<DemoStage, number> = {
  typing: 0, // driven by character count
  grounded: 2200,
  sql: 2600,
  quality: 2000,
  answer: 2800,
  pause: 1800,
};

export function HeroLiveDemo({ className }: { className?: string }) {
  const [scriptIndex, setScriptIndex] = React.useState(0);
  const [stage, setStage] = React.useState<DemoStage>("typing");
  const [typed, setTyped] = React.useState("");
  const [reduceMotion, setReduceMotion] = React.useState(false);
  const script = SCRIPTS[scriptIndex]!;

  React.useEffect(() => {
    setReduceMotion(window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }, []);

  React.useEffect(() => {
    if (reduceMotion) {
      setTyped(script.question);
      setStage("answer");
      return;
    }

    let cancelled = false;
    let timer: number | undefined;

    async function run() {
      setStage("typing");
      setTyped("");
      for (let i = 0; i <= script.question.length; i += 1) {
        if (cancelled) return;
        setTyped(script.question.slice(0, i));
        await wait(28 + (script.question[i] === " " ? 40 : 0));
      }
      if (cancelled) return;
      setStage("grounded");
      await wait(STAGE_MS.grounded);
      if (cancelled) return;
      setStage("sql");
      await wait(STAGE_MS.sql);
      if (cancelled) return;
      setStage("quality");
      await wait(STAGE_MS.quality);
      if (cancelled) return;
      setStage("answer");
      await wait(STAGE_MS.answer);
      if (cancelled) return;
      setStage("pause");
      await wait(STAGE_MS.pause);
      if (cancelled) return;
      setScriptIndex((index) => (index + 1) % SCRIPTS.length);
    }

    void run();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };

    function wait(ms: number) {
      return new Promise<void>((resolve) => {
        timer = window.setTimeout(resolve, ms);
      });
    }
  }, [scriptIndex, script.question, reduceMotion]);

  const maxBar = Math.max(...script.bars, 1);
  const showGrounded = stage !== "typing";
  const showSql = stage === "sql" || stage === "quality" || stage === "answer" || stage === "pause";
  const showQuality = stage === "quality" || stage === "answer" || stage === "pause";
  const showAnswer = stage === "answer" || stage === "pause";

  return (
    <div
      id="how-it-works"
      className={cn(
        "relative overflow-hidden rounded-[var(--radius-card)] border border-border/70 bg-card/80 p-4 shadow-[var(--shadow-raised)] backdrop-blur-sm",
        "hero-demo-surface",
        className,
      )}
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
          Live demo · {script.domain}
        </p>
        <span className="rounded-full border border-border/70 px-2 py-0.5 text-[10px] text-muted-foreground">
          Example sequence
        </span>
      </div>

      <div className="rounded-xl border border-border/60 bg-background px-3 py-2.5">
        <p className="min-h-[2.75rem] text-sm leading-relaxed text-foreground">
          {typed}
          {stage === "typing" ? (
            <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-primary align-middle" />
          ) : null}
        </p>
      </div>

      <div
        className={cn(
          "mt-3 transition-opacity duration-500",
          showGrounded ? "opacity-100" : "opacity-0",
        )}
      >
        <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/25 bg-primary/8 px-2.5 py-1 text-[11px] font-medium text-primary">
          <Check className="size-3" aria-hidden="true" />
          Grounded in semantic layer
        </span>
      </div>

      <div
        className={cn(
          "mt-3 transition-opacity duration-500",
          showSql ? "opacity-100" : "pointer-events-none opacity-0",
        )}
      >
        <SQLViewer sql={script.sql} compact />
      </div>

      <div
        className={cn(
          "mt-3 transition-opacity duration-500",
          showQuality ? "opacity-100" : "opacity-0",
        )}
      >
        <span className="inline-flex items-center gap-1.5 rounded-full border border-success/30 bg-success/10 px-2.5 py-1 text-[11px] font-medium text-success">
          <Check className="size-3" aria-hidden="true" />
          Data quality check passed
        </span>
      </div>

      <div
        className={cn(
          "mt-3 rounded-xl border border-border/60 bg-muted/30 p-3 transition-opacity duration-500 dark:bg-muted/15",
          showAnswer ? "opacity-100" : "pointer-events-none opacity-0",
        )}
      >
        <p className="text-[11px] text-muted-foreground">{script.answerLabel}</p>
        <p className="mt-1 text-sm font-semibold text-foreground">{script.answerValue}</p>
        <div className="mt-3 flex h-16 items-end gap-1.5">
          {script.bars.map((value, index) => (
            <div
              key={`${script.domain}-${index}`}
              className="flex-1 rounded-t"
              style={{
                height: `${Math.max((value / maxBar) * 100, 8)}%`,
                backgroundColor: index === 0 ? CHART_SERIES.primary : CHART_SERIES.secondary,
                opacity: 0.45 + (value / maxBar) * 0.55,
              }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
