export interface CostEstimate {
  /** Blended USD per 1M tokens at the assumed input/output split. */
  per1mTokens: number;
  perQuestion: number;
  /** Whole questions $1 buys; null when the model is free (local). */
  questionsPerDollar: number | null;
}

export function estimateCost(
  inputUsdPer1m: number | null,
  outputUsdPer1m: number | null,
  inputTokens: number,
  outputTokens: number,
): CostEstimate | null {
  if (inputUsdPer1m == null || outputUsdPer1m == null) return null;
  const tokens = inputTokens + outputTokens;
  if (tokens <= 0) return null;
  const perQuestion = (inputUsdPer1m * inputTokens + outputUsdPer1m * outputTokens) / 1_000_000;
  return {
    per1mTokens: (perQuestion / tokens) * 1_000_000,
    perQuestion,
    questionsPerDollar: perQuestion > 0 ? Math.floor(1 / perQuestion) : null,
  };
}

/** Whole questions a budget buys; null when the model is free (local). */
export function questionsForBudget(estimate: CostEstimate, budgetUsd: number): number | null {
  return estimate.perQuestion > 0 ? Math.floor(budgetUsd / estimate.perQuestion) : null;
}

/** USD for a token count at the blended rate. */
export function costOfTokens(estimate: CostEstimate, tokens: number): number {
  return (estimate.per1mTokens * tokens) / 1_000_000;
}

export function formatUsd(value: number): string {
  if (value === 0) return "$0";
  if (value < 0.01) return `$${value.toPrecision(2)}`;
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
