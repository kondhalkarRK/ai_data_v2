"use client";

import * as React from "react";

/** Width/height of an element, kept in sync with ResizeObserver. */
export function useElementSize<T extends HTMLElement>(): [
  (node: T | null) => void,
  { width: number; height: number },
] {
  const [node, setNode] = React.useState<T | null>(null);
  const [size, setSize] = React.useState({ width: 0, height: 0 });
  React.useLayoutEffect(() => {
    if (!node) return;
    const update = () => {
      const rect = node.getBoundingClientRect();
      setSize((prev) =>
        Math.abs(prev.width - rect.width) < 1 && Math.abs(prev.height - rect.height) < 1
          ? prev
          : { width: rect.width, height: rect.height },
      );
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => observer.disconnect();
  }, [node]);
  return [setNode, size];
}

export function niceMax(value: number, ticks = 4): { max: number; step: number } {
  if (value <= 0) return { max: 1, step: 0.25 };
  const raw = value / ticks;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((n) => n * pow).find((n) => n >= raw) ?? raw;
  return { max: Math.ceil(value / step) * step, step };
}

type Point = [number, number];

/** Monotone cubic (Fritsch–Carlson) path: smooth without overshooting the data. */
export function monotonePath(points: Point[]): string {
  const n = points.length;
  if (n === 0) return "";
  if (n === 1) return `M${points[0]![0]},${points[0]![1]}`;
  const dx: number[] = [];
  const slope: number[] = [];
  for (let i = 0; i < n - 1; i++) {
    const h = points[i + 1]![0] - points[i]![0];
    dx.push(h);
    slope.push(h === 0 ? 0 : (points[i + 1]![1] - points[i]![1]) / h);
  }
  const tangent: number[] = [slope[0]!];
  for (let i = 1; i < n - 1; i++) {
    const a = slope[i - 1]!;
    const b = slope[i]!;
    tangent.push(a * b <= 0 ? 0 : (3 * (dx[i - 1]! + dx[i]!)) / ((2 * dx[i]! + dx[i - 1]!) / a + (dx[i]! + 2 * dx[i - 1]!) / b));
  }
  tangent.push(slope[n - 2]!);
  let d = `M${points[0]![0]},${points[0]![1]}`;
  for (let i = 0; i < n - 1; i++) {
    const [x0, y0] = points[i]!;
    const [x1, y1] = points[i + 1]!;
    const h = dx[i]! / 3;
    d += ` C${x0 + h},${y0 + tangent[i]! * h} ${x1 - h},${y1 - tangent[i + 1]! * h} ${x1},${y1}`;
  }
  return d;
}

/** Splits a series with gaps (null) into continuous runs. */
export function runs<T>(items: T[], value: (item: T) => number | null): Array<Array<[number, number]>> {
  const out: Array<Array<[number, number]>> = [];
  let current: Array<[number, number]> = [];
  items.forEach((item, index) => {
    const v = value(item);
    if (v == null) {
      if (current.length) out.push(current);
      current = [];
    } else current.push([index, v]);
  });
  if (current.length) out.push(current);
  return out;
}

const STYLE_PROPS = [
  "fill",
  "fill-opacity",
  "stroke",
  "stroke-width",
  "stroke-opacity",
  "stroke-dasharray",
  "opacity",
  "font-size",
  "font-family",
  "font-weight",
  "text-anchor",
  "dominant-baseline",
] as const;

function download(href: string, filename: string): void {
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

/** Renders an on-page SVG to a PNG download, inlining computed styles. */
export async function exportSvgPng(svg: SVGSVGElement, filename: string): Promise<void> {
  const rect = svg.getBoundingClientRect();
  const clone = svg.cloneNode(true) as SVGSVGElement;
  const source = [svg, ...Array.from(svg.querySelectorAll("*"))];
  const target = [clone, ...Array.from(clone.querySelectorAll("*"))];
  source.forEach((node, index) => {
    const style = window.getComputedStyle(node);
    const copy = target[index] as SVGElement | undefined;
    if (!copy) return;
    for (const prop of STYLE_PROPS) {
      const value = style.getPropertyValue(prop);
      if (value) copy.style.setProperty(prop, value);
    }
  });
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("width", String(rect.width));
  clone.setAttribute("height", String(rect.height));
  const data = new XMLSerializer().serializeToString(clone);
  const url = URL.createObjectURL(new Blob([data], { type: "image/svg+xml;charset=utf-8" }));
  try {
    const image = new Image();
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error("SVG render failed"));
      image.src = url;
    });
    const scale = 2;
    const canvas = document.createElement("canvas");
    canvas.width = rect.width * scale;
    canvas.height = rect.height * scale;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.scale(scale, scale);
    ctx.drawImage(image, 0, 0, rect.width, rect.height);
    download(canvas.toDataURL("image/png"), filename);
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function exportCsv(rows: Array<Record<string, unknown>>, filename: string): void {
  if (!rows.length) return;
  const headers = Object.keys(rows[0]!);
  const escape = (value: unknown) => {
    const text = value == null ? "" : String(value);
    return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  };
  const csv = [headers.join(","), ...rows.map((row) => headers.map((h) => escape(row[h])).join(","))].join("\n");
  const url = URL.createObjectURL(new Blob([`\ufeff${csv}`], { type: "text/csv;charset=utf-8" }));
  download(url, filename);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
