import { describe, expect, it } from "vitest";

import { visibleSections } from "@/lib/navigation";

function labelsFor(role: Parameters<typeof visibleSections>[0]): string[] {
  return visibleSections(role).flatMap((section) => section.items.map((item) => item.label));
}

const CORE = [
  "Executive Intelligence",
  "AI Chat",
  "Data Trust",
  "Semantic Atlas",
  "Knowledge Graph (Beta)",
];

describe("sidebar visibility", () => {
  it("gives a user the core workspace and their usage, but no admin menu", () => {
    const labels = labelsFor("user");
    for (const label of CORE) expect(labels).toContain(label);
    expect(labels).toContain("My AI Usage");
    expect(labels).not.toContain("Admin Center");
    expect(visibleSections("user").some((s) => s.id === "admin")).toBe(false);
  });

  it("gives an admin the same workspace plus the Admin Center", () => {
    const labels = labelsFor("admin");
    for (const label of CORE) expect(labels).toContain(label);
    expect(labels).toContain("Admin Center");
  });

  it("lists the core workspace first, in the governed order", () => {
    expect(visibleSections("user")[0]?.items.map((item) => item.label)).toEqual(CORE);
  });

  it("drops a section once every item in it is filtered away", () => {
    for (const section of visibleSections("user")) {
      expect(section.items.length).toBeGreaterThan(0);
    }
  });
});
