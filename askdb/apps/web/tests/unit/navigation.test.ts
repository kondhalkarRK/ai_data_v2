import { describe, expect, it } from "vitest";

import { NAV_SECTIONS, visibleSections } from "@/lib/navigation";

function labelsFor(role: Parameters<typeof visibleSections>[0]): string[] {
  return visibleSections(role).flatMap((section) => section.items.map((item) => item.label));
}

describe("sidebar visibility", () => {
  it("hides analyst and admin destinations from a viewer", () => {
    const labels = labelsFor("viewer");
    expect(labels).not.toContain("AI Chat");
    expect(labels).not.toContain("LLM Observability");
    expect(labels).not.toContain("System Logs");
    expect(labels).toContain("Executive Intelligence");
    expect(labels).toContain("Semantic Atlas");
  });

  it("gives an analyst chat and LLM observability, but not system logs", () => {
    const labels = labelsFor("analyst");
    expect(labels).toContain("AI Chat");
    expect(labels).toContain("LLM Observability");
    expect(labels).not.toContain("System Logs");
  });

  it("shows an admin everything", () => {
    const everything = NAV_SECTIONS.flatMap((section) =>
      section.items.map((item) => item.label),
    );
    expect(labelsFor("admin")).toEqual(everything);
  });

  it("drops a section once every item in it is filtered away", () => {
    // An empty heading with nothing under it is a layout bug, not a design choice.
    for (const section of visibleSections("viewer")) {
      expect(section.items.length).toBeGreaterThan(0);
    }
  });
});
