import { describe, expect, it } from "vitest";

import { estimateCost, formatUsd } from "@/lib/llm-cost";

describe("estimateCost", () => {
  it("blends input and output prices at the assumed token split", () => {
    // GPT-5 mini: $0.25 in / $2.00 out, 2,000 in + 500 out per question.
    const estimate = estimateCost(0.25, 2, 2000, 500)!;
    expect(estimate.perQuestion).toBeCloseTo(0.0015, 6);
    expect(estimate.per1mTokens).toBeCloseTo(0.6, 6);
    expect(estimate.questionsPerDollar).toBe(666);
  });

  it("treats a free local model as unlimited", () => {
    const estimate = estimateCost(0, 0, 2000, 500)!;
    expect(estimate.perQuestion).toBe(0);
    expect(estimate.questionsPerDollar).toBeNull();
  });

  it("returns null when the model has no pricing", () => {
    expect(estimateCost(null, 2, 2000, 500)).toBeNull();
  });
});

describe("formatUsd", () => {
  it("keeps small amounts readable", () => {
    expect(formatUsd(0.0015)).toBe("$0.0015");
    expect(formatUsd(1.25)).toBe("$1.25");
    expect(formatUsd(0)).toBe("$0");
  });
});
