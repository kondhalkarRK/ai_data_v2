import { act, render, renderHook, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { formatInr, formatPct } from "@/components/executive/cockpit/format";
import { tint } from "@/components/executive/cockpit/palette";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { useCountUp } from "@/hooks/use-count-up";

let now = 0;
let id = 0;
let frames: Map<number, FrameRequestCallback>;

function advance(ms: number) {
  now += ms;
  const pending = [...frames.values()];
  frames.clear();
  act(() => pending.forEach((callback) => callback(now)));
}

beforeEach(() => {
  now = 0;
  frames = new Map();
  vi.spyOn(performance, "now").mockImplementation(() => now);
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    frames.set(++id, callback);
    return id;
  });
  vi.stubGlobal("cancelAnimationFrame", (key: number) => frames.delete(key));
});

afterEach(() => vi.unstubAllGlobals());

describe("metric transitions", () => {
  it("continues from the current value on rapid updates and cancels on unmount", () => {
    const { result, rerender, unmount } = renderHook(({ value }) => useCountUp(value), {
      initialProps: { value: 100 },
    });
    advance(0); // viewport fallback
    advance(700);
    expect(result.current.display).toBe(100);
    rerender({ value: 200 });
    expect(result.current.display).toBe(100);
    advance(350);
    const intermediate = result.current.display;
    expect(intermediate).toBeGreaterThan(100);
    expect(intermediate).toBeLessThan(200);
    rerender({ value: -50 });
    expect(result.current.display).toBe(intermediate);
    advance(700);
    expect(result.current.display).toBe(-50);
    rerender({ value: -50 });
    expect(frames.size).toBe(0);
    rerender({ value: 300 });
    unmount();
    expect(frames.size).toBe(0);
  });

  it("settles immediately with reduced motion", () => {
    vi.spyOn(window, "matchMedia").mockReturnValue({
      matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn(),
    } as unknown as MediaQueryList);
    const { result } = renderHook(() => useCountUp(98.4, { decimals: 1 }));
    advance(0);
    advance(0);
    expect(result.current.display).toBe(98.4);
    expect(frames.size).toBe(0);
  });

  it("exposes the final formatted value accessibly and keeps missing values distinct", () => {
    const { container, rerender } = render(<AnimatedNumber value={12500000} format={formatInr} />);
    expect(container.querySelector(".sr-only")).toHaveTextContent("₹1.3 Cr");
    advance(0);
    advance(700);
    expect(container.querySelector('[aria-hidden="true"]')).toHaveTextContent("₹1.3 Cr");
    rerender(<AnimatedNumber value={null} />);
    expect(container.querySelector('[aria-hidden="true"]')).toHaveTextContent("—");
    rerender(<AnimatedNumber value={0} />);
    advance(700);
    expect(container.querySelector('[aria-hidden="true"]')).toHaveTextContent("0");
    rerender(<AnimatedNumber value={-0.125} format={formatPct} decimals={3} />);
    advance(700);
    expect(screen.getAllByText("-12.5%")).toHaveLength(2);
    rerender(<AnimatedNumber value={Infinity} />);
    expect(container.querySelector('[aria-hidden="true"]')).toHaveTextContent("—");
  });

  it("tints token-backed graph colors without parsing them as hex", () => {
    expect(tint("hsl(var(--primary))", 0.2)).toBe("color-mix(in srgb, hsl(var(--primary)) 80%, white)");
    expect(tint("#000000", 0.5)).toBe("#808080");
  });
});
