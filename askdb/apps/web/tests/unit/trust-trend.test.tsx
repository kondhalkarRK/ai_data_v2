import type { ReactNode } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/executive/cockpit/chart-frame", () => ({
  ChartFrame: ({ children, subtitle, controls }: { children: (expanded: boolean) => ReactNode; subtitle: ReactNode; controls: ReactNode }) => <section>{subtitle}{controls}{children(false)}</section>,
  ChartTooltip: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  Segmented: ({ options, onChange }: { options: { value: string; label: string }[]; onChange: (value: string) => void }) => <div>{options.map(o => <button key={o.value} onClick={() => onChange(o.value)}>{o.label}</button>)}</div>,
}));
vi.mock("@/components/executive/cockpit/chart-utils", async importOriginal => ({
  ...await importOriginal<object>(),
  useElementSize: () => [() => {}, { width: 700, height: 236 }],
}));

import { TrustTrendChart } from "@/components/reliability/trust-trend";
import type { DataReliability, TrustTrend } from "@/components/reliability/types";

function mount(points: TrustTrend["points"]) {
  const data = { trend: { points, events: [], basis: "Recorded daily history", measuredRuns: 1, endDate: "2026-11-24" } } as unknown as DataReliability;
  return render(<TrustTrendChart data={data} filters={{}} onOpenRule={() => {}} />);
}

describe("Recorded trust trend", () => {
  it("does not draw a historical line when no measurements exist", () => {
    const { container } = mount([]);
    expect(screen.getByText(/No recorded scores in this period/)).toBeVisible();
    expect(container.querySelector("svg")).toBeNull();
  });

  it("explains a single measured day instead of suggesting a full history", () => {
    const { container } = mount([{ date: "2026-11-24", score: 91, measured: 91, dimensions: {} }]);
    expect(screen.getByText(/One recorded day so far/)).toBeVisible();
    expect(container.querySelector("circle title")?.textContent).toContain("91.0");
    expect(screen.getByText(/latest check per UTC day/)).toBeVisible();
  });

  it("keeps missing days empty and filters the selected calendar window", () => {
    mount(Array.from({ length: 30 }, (_, i) => ({
      date: new Date(Date.UTC(2026, 9, 26 + i)).toISOString().slice(0, 10),
      score: i === 0 ? 80 : null, measured: i === 0 ? 80 : null, dimensions: {},
    })));
    expect(screen.getByText(/One recorded day/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "7D" }));
    expect(screen.getByText(/No recorded scores in this period/)).toBeVisible();
  });
});
