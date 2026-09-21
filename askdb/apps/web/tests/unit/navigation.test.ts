import { describe, expect, it } from "vitest";

import { visibleSections } from "@/lib/navigation";

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
    expect(labels).toContain("Home");
    expect(labels).not.toContain("Data Sources");
  });

  it("gives an analyst chat, analytics builder, and LLM observability, but not system logs", () => {
    const labels = labelsFor("analyst");
    expect(labels).toContain("AI Chat");
    expect(labels).toContain("Analytics Builder");
    expect(labels).toContain("Ontology Browser");
    expect(labels).toContain("LLM Observability");
    expect(labels).not.toContain("System Logs");
  });

  it("shows an admin everything including system logs under Admin", () => {
    expect(labelsFor("admin")).toContain("System Logs");
    expect(visibleSections("admin").some((s) => s.id === "admin")).toBe(true);
  });

  it("drops a section once every item in it is filtered away", () => {
    // An empty heading with nothing under it is a layout bug, not a design choice.
    for (const section of visibleSections("viewer")) {
      expect(section.items.length).toBeGreaterThan(0);
    }
  });
});
