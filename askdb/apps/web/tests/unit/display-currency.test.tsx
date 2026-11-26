import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DISPLAY_CURRENCY, DISPLAY_CURRENCY_NOTE, formatRevenueInr, isMonetaryColumn } from "@/lib/display-currency";
import { formatReportValue } from "@/components/analytics-builder/askbi/report-format";
import { ResultChart } from "@/components/chat/result-chart";
import { formatInr, formatCount, formatPct } from "@/components/executive/cockpit/format";

describe("Approved INR to USD display", () => {
  it("divides by 95, discloses provenance and leaves source values unchanged", () => {
    const row = { revenue: 95000000, units: 95 };
    expect(formatRevenueInr(row.revenue)).toBe("$1M");
    expect(formatInr(95000)).toBe("$1K");
    expect(formatReportValue(-95000, "currency")).toBe("-$1K");
    expect(formatRevenueInr(9500, false)).toBe("$100.00");
    expect(formatRevenueInr(0)).toBe("$0");
    expect(formatRevenueInr(Infinity)).toBe("—");
    expect(row).toEqual({ revenue: 95000000, units: 95 });
    expect(DISPLAY_CURRENCY.inrPerUsd).toBe(95);
    expect(DISPLAY_CURRENCY_NOTE).toContain(DISPLAY_CURRENCY.configuredOn);
    expect(DISPLAY_CURRENCY_NOTE).toContain("not a live market rate");
    expect(formatCount(95)).toBe("95");
    expect(formatPct(0.25)).toBe("25.0%");
    expect(formatReportValue(95, "integer")).toBe("95");
    expect(formatReportValue(25, "percent")).toBe("25%");
  });

  it("does not classify counts, percentage changes or shares as money", () => {
    for (const key of ["revenue_growth_pct", "revenue_share", "units_sold", "order_count", "profit_margin"]) expect(isMonetaryColumn(key)).toBe(false);
    for (const key of ["revenue", "total_sales", "avg_price", "asp", "net_revenue"]) expect(isMonetaryColumn(key)).toBe(true);
  });

  it("shows USD axes and exact USD tooltips for revenue charts", () => {
    const { container } = render(<ResultChart rows={[{ model: "A", revenue: 95000 }]} xKey="model" yKey="revenue" />);
    expect(screen.getByText(DISPLAY_CURRENCY_NOTE)).toBeVisible();
    expect(container.querySelector("svg")?.textContent).toContain("$");
    const bar = container.querySelector("svg rect[rx]");
    expect(bar).not.toBeNull();
    fireEvent.mouseEnter(bar!);
    expect(screen.getByText(/revenue: \$1,000\.00/)).toBeVisible();
  });

  it("keeps count charts in their original units", () => {
    const { container } = render(<ResultChart rows={[{ model: "A", units_sold: 95 }]} xKey="model" yKey="units_sold" />);
    expect(screen.queryByText(DISPLAY_CURRENCY_NOTE)).toBeNull();
    expect(container.querySelector("svg")?.textContent).not.toContain("$");
  });

  it("does not convert counts when changing metrics on a currency result", () => {
    const { container } = render(<ResultChart rows={[{ model: "A", revenue: 95000, units_sold: 95 }]} xKey="model" yKey="revenue" metricFormat="currency" series={["revenue", "units_sold"]} />);
    expect(screen.queryByRole("option", { name: "All series" })).toBeNull();
    fireEvent.change(screen.getByLabelText("Y Axis"), { target: { value: "units_sold" } });
    expect(container.querySelector("svg")?.textContent).not.toContain("$");
    expect(screen.queryByText(DISPLAY_CURRENCY_NOTE)).toBeNull();
  });
});
