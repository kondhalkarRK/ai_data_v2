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
});
