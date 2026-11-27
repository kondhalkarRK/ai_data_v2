import { describe, expect, it } from "vitest";

import { formatChatCell, isPeriodColumn } from "@/lib/format-chat-cell";

describe("formatChatCell", () => {
  it("shortens ISO dates on period columns", () => {
    expect(formatChatCell("2015-04-01", "quarter")).toBe("2015-04");
    expect(formatChatCell("2015-01-01", "month")).toBe("2015-01");
  });

  it("leaves non-period columns unchanged", () => {
    expect(formatChatCell("2015-04-01", "dealer_name")).toBe("2015-04-01");
  });

  it("detects half-year columns", () => {
    expect(isPeriodColumn("half")).toBe(true);
    expect(formatChatCell("2015-07-01", "half")).toBe("2015-07");
  });

  it("formats comparison revenue columns without changing counts, periods or exact source values", () => {
    expect(formatChatCell(1796236300, "beta_revenue")).toBe("₹179.62 Cr");
    expect(formatChatCell(834029.5, "value", "currency")).toBe("₹8.34 Lakh");
    expect(formatChatCell(2026, "year")).toBe("2026");
    expect(formatChatCell(12345, "units_sold")).toBe("12345");
    expect(formatChatCell(5, "revenue_growth_pct", "percent")).toBe("5");
    expect(formatChatCell(null, "beta_revenue")).toBe("—");
    expect(formatChatCell(0, "beta_revenue")).toBe("₹0");
  });
});
