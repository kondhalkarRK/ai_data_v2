import { fireEvent, render, screen } from "@testing-library/react";
import * as React from "react";
import { describe, expect, it } from "vitest";

import { InsightSummary } from "@/components/chat/insight-summary";
import type { InsightDepth, NarrationSections } from "@/components/chat/types";

const NARRATION: NarrationSections = {
  summary: "Maruti leads units sold at 4,200, 42% of the total.",
  highlights: ["Top 3 contribute 88% of the total.", "MG trails at 300.", "Median across 5 makes: 2,100."],
  insight: "Maruti is a clear outlier.",
  focus: null,
};

function Harness() {
  const [depth, setDepth] = React.useState<InsightDepth>("executive");
  return (
    <InsightSummary executive="" analyst="" narration={NARRATION} depth={depth} onDepthChange={setDepth} />
  );
}

describe("InsightSummary narration", () => {
  it("shows only the relevant sections and more highlights in analyst depth", () => {
    render(<Harness />);
    expect(screen.getByText("Executive Summary")).toBeInTheDocument();
    expect(screen.getByText("Business Insight")).toBeInTheDocument();
    expect(screen.queryByText("Recommended Focus Area")).not.toBeInTheDocument();
    expect(screen.queryByText("Median across 5 makes: 2,100.")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "analyst" }));
    expect(screen.getByText("Median across 5 makes: 2,100.")).toBeInTheDocument();
  });
});
