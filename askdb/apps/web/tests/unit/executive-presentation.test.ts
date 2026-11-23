import { afterEach, expect, it, vi } from "vitest";
import { animateChart } from "@/components/executive/cockpit/chart-motion";
import { categoryColour, vibrantColour } from "@/components/executive/cockpit/palette";
import { exportSvgPng } from "@/components/executive/cockpit/chart-utils";

afterEach(() => { vi.restoreAllMocks(); document.body.innerHTML = ""; });

it("keeps category identity stable across ordering and preserves a Classic fallback", () => {
  const original = ["make:Alpha", "make:Beta", "make:Gamma"];
  const colours = new Map(original.map(key => [key, categoryColour(key)]));
  for (const key of [...original].reverse().slice(1)) expect(categoryColour(key)).toBe(colours.get(key));
  expect(categoryColour("MAKE:ALPHA")).toBe(colours.get("make:Alpha"));
  expect(vibrantColour("fuel:Electric", "#123456")).toMatch(/^var\(--executive-vibrant-category-\d+, #123456\)$/);
});

it("waits for SVG layout, animates once, and finishes on reduced-motion changes", async () => {
  const media = { matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() };
  vi.spyOn(window, "matchMedia").mockReturnValue(media as unknown as MediaQueryList);
  const body = document.createElement("div"); document.body.append(body);
  const cleanup = animateChart(body);
  const mark = document.createElement("span"); mark.dataset.chartGrow = "";
  const finish = vi.fn(), cancel = vi.fn();
  mark.animate = vi.fn().mockReturnValue({ finish, cancel }); body.append(mark);
  await Promise.resolve();
  expect(mark.animate).toHaveBeenCalledTimes(1);
  expect(mark.animate).toHaveBeenCalledWith(expect.any(Array), expect.objectContaining({ duration: 650 }));
  body.append(document.createElement("span")); await Promise.resolve();
  expect(mark.animate).toHaveBeenCalledTimes(1);
  media.matches = true; media.addEventListener.mock.calls[0]![1]();
  expect(finish).toHaveBeenCalledTimes(1);
  cleanup(); expect(cancel).toHaveBeenCalledTimes(1);
  expect(media.removeEventListener).toHaveBeenCalled();
});

it("leaves reduced-motion charts fully visible and static", () => {
  vi.spyOn(window, "matchMedia").mockReturnValue({ matches: true } as MediaQueryList);
  const body = document.createElement("div"), mark = document.createElement("span");
  mark.dataset.chartReveal = ""; mark.animate = vi.fn(); body.append(mark);
  animateChart(body)(); expect(mark.animate).not.toHaveBeenCalled();
});

it("finishes chart animations before PNG capture begins", async () => {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  const finish = vi.fn();
  svg.getAnimations = vi.fn().mockReturnValue([{ finish, effect: { getTiming: () => ({ iterations: 1 }) } }]);
  vi.spyOn(svg, "getBoundingClientRect").mockImplementation(() => { expect(finish).toHaveBeenCalledOnce(); throw new Error("capture boundary"); });
  await expect(exportSvgPng(svg, "chart.png")).rejects.toThrow("capture boundary");
});
