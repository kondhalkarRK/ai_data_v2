import { zipReportFiles } from "./report-zip";
import type { BiReport } from "@nql/shared-types";
import { reportReady, type PanelResult } from "./use-askbi";

export type ReportSnapshot = {
  report: BiReport; results: Record<string, PanelResult>; briefing: string[];
  scopeLabel: string; liftPercent: number; root: HTMLElement;
};
function freeze<T>(value: T): T {
  if (value && typeof value === "object") {
    Object.freeze(value);
    for (const child of Object.values(value)) freeze(child);
  }
  return value;
}

/** Synchronous snapshot: no auth, saving, narration or analytical requests. */
export function createReportSnapshot(report: BiReport, results: Record<string, PanelResult>, briefing: string[], root: HTMLElement, scopeLabel: string, liftPercent: number): ReportSnapshot {
  if (!reportReady(report.state.plan, results)) throw new Error("Wait for all current panels before exporting.");
  const data = freeze(structuredClone({ report, results, briefing, scopeLabel, liftPercent }));
  const clone = root.cloneNode(true) as HTMLElement;
  clone.querySelectorAll<HTMLElement>("[data-export-value]").forEach(node => { node.textContent = node.dataset.exportValue ?? "—"; });
  clone.querySelectorAll("button, select, details, input[type=range]").forEach(node => node.remove());
  // Do not capture stale transition/animation frames or controls.
  clone.querySelectorAll<HTMLElement>("*").forEach(node => { node.style.animation = "none"; node.style.transition = "none"; });
  return { ...data, root: clone };
}

export function assertReportCanvas(canvas: HTMLCanvasElement): void {
  if (!canvas.width || !canvas.height) throw new Error("A report section could not be captured.");
  const pixels = canvas.getContext("2d")?.getImageData(0, 0, canvas.width, canvas.height).data;
  if (!pixels?.length) throw new Error("Report image pixels could not be verified.");
  const stride = Math.max(1, Math.floor(pixels.length / 4 / 50000)) * 4;
  for (let i = 0; i < pixels.length; i += stride) {
    if (Math.abs(pixels[i]! - pixels[0]!) + Math.abs(pixels[i + 1]! - pixels[1]!) + Math.abs(pixels[i + 2]! - pixels[2]!) > 24) return;
  }
  throw new Error("A blank report image was detected. Nothing was exported; use Export PDF or retry.");
}

/** Resolve modern CSS colors through the browser before the canvas parser sees them. */
function normalizeCaptureColors(doc: Document, target: HTMLElement): void {
  const probe = document.createElement("canvas"); probe.width = 1; probe.height = 1;
  const context = probe.getContext("2d");
  if (!context) throw new Error("Color conversion is unavailable.");
  const cache = new Map<string, string>();
  const convert = (value: string) => {
    if (!value || value === "none" || value.startsWith("url(")) return value;
    const known = cache.get(value); if (known) return known;
    context.clearRect(0, 0, 1, 1); context.fillStyle = value; context.fillRect(0, 0, 1, 1);
    const [r, g, b, a] = context.getImageData(0, 0, 1, 1).data;
    const rgba = `rgba(${r},${g},${b},${(a ?? 255) / 255})`; cache.set(value, rgba); return rgba;
  };
  const nodes = new Set<Element>([target, ...target.querySelectorAll("*")]);
  for (let parent = target.parentElement; parent; parent = parent.parentElement) nodes.add(parent);
  for (const element of nodes) {
    const style = doc.defaultView?.getComputedStyle(element);
    if (!style) continue;
    const node = element as HTMLElement | SVGElement;
    for (const property of ["color", "background-color", "border-top-color", "border-right-color", "border-bottom-color", "border-left-color", "outline-color", "text-decoration-color", "fill", "stroke"]) {
      node.style.setProperty(property, convert(style.getPropertyValue(property)));
    }
    node.style.boxShadow = "none";
  }
}

function expandScrollableContent(root: HTMLElement): void {
  root.querySelectorAll<HTMLElement>("*").forEach(node => {
    if (node.classList.contains("truncate")) {
      node.style.overflow = "visible";
      node.style.whiteSpace = "normal";
      node.style.lineHeight = "1.5";
      node.style.paddingBlock = "2px";
    }
    const style = getComputedStyle(node);
    if ([style.overflow, style.overflowX, style.overflowY].some(value => value === "auto" || value === "scroll")) {
      node.style.overflow = "visible";
      node.style.maxHeight = "none";
      node.style.height = "auto";
    }
  });
}

export async function captureReport(snapshot: ReportSnapshot) {
  const html2canvas = (await import("html2canvas")).default;
  const { jsPDF } = await import("jspdf");
  const host = document.createElement("div");
  host.className = "askbi-export-paper";
  Object.assign(host.style, { position: "absolute", left: "-100000px", top: "0", width: "1120px", padding: "24px", background: "white", pointerEvents: "none" });
  const root = snapshot.root.cloneNode(true) as HTMLElement;
  host.append(root); document.body.append(host);
  try {
    await document.fonts?.ready;
    expandScrollableContent(root);
    const capture = async (element: HTMLElement) => {
      const canvas = await html2canvas(element, { scale: 1.5, backgroundColor: "#ffffff", foreignObjectRendering: false, onclone: normalizeCaptureColors });
      assertReportCanvas(canvas);
      return canvas;
    };
    const blocks = [...root.querySelectorAll<HTMLElement>("[data-askbi-pdf]")];
    if (!blocks.length) throw new Error("The report has no exportable sections.");
    const pdf = new jsPDF({ orientation: "landscape", unit: "mm", format: "a4" });
    let cursor = 12;
    for (const block of blocks) {
      const canvas = await capture(block);
      const width = Math.min(273, 174 * canvas.width / canvas.height);
      const height = canvas.height * width / canvas.width;
      if (cursor + height > 198) { pdf.addPage(); cursor = 12; }
      pdf.addImage(canvas.toDataURL("image/png"), "PNG", 12, cursor, width, height);
      cursor += height + 5;
    }
    const pictures: Array<{ title: string; panelId: string; dataUrl: string }> = [];
    for (const panel of snapshot.report.state.plan!.panels.filter(panel => panel.kind !== "kpi")) {
      const element = [...root.querySelectorAll<HTMLElement>("[id^=askbi-panel-]")].find(node => node.id === `askbi-panel-${panel.id}`);
      // The prior region series is intentionally represented by its reconciled comparison.
      if (!element && panel.id === "revenue-lift-region-baseline" && root.querySelector('[aria-label="Observed revenue change by region"]')) continue;
      if (!element) throw new Error(`Missing report panel: ${panel.title}. Nothing was exported.`);
      pictures.push({ title: element.querySelector("h3")?.textContent || panel.title, panelId: panel.id, dataUrl: (await capture(element)).toDataURL("image/png") });
    }
    return { pictures, pdfDataUrl: pdf.output("datauristring") };
  } finally { host.remove(); }
}

function download(url: string, name: string) {
  const link = document.createElement("a"); link.href = url; link.download = name; link.click();
}

/** Each image is one PDF page, keeping long reports readable when pasted. */
export async function reportImages(snapshot: ReportSnapshot): Promise<Blob[]> {
  const html2canvas = (await import("html2canvas")).default;
  const host = document.createElement("div");
  host.className = "askbi-export-paper";
  Object.assign(host.style, { position: "absolute", left: "-100000px", top: "0", width: "1120px", padding: "24px", background: "white" });
  host.append(snapshot.root.cloneNode(true)); document.body.append(host);
  try {
    await document.fonts?.ready;
    expandScrollableContent(host);
    const blocks = [...host.querySelectorAll<HTMLElement>("[data-askbi-pdf]")];
    if (!blocks.length) throw new Error("No report sections are available to capture.");
    const blobs: Blob[] = [];
    let page: HTMLCanvasElement | null = null;
    let cursor = 0;
    const finish = async () => {
      if (!page || !cursor) return;
      const cropped = document.createElement("canvas"); cropped.width = page.width; cropped.height = cursor;
      const context = cropped.getContext("2d");
      if (!context) throw new Error("Image capture is unavailable.");
      context.drawImage(page, 0, 0);
      blobs.push(await new Promise<Blob>((resolve, reject) => cropped.toBlob(blob => blob ? resolve(blob) : reject(new Error("PNG encoding failed.")), "image/png")));
      page = null; cursor = 0;
    };
    for (const block of blocks) {
      const canvas = await html2canvas(block, { scale: 1.5, backgroundColor: "#ffffff", foreignObjectRendering: false, onclone: normalizeCaptureColors });
      assertReportCanvas(canvas);
      const width = 1608;
      const height = Math.ceil(canvas.height * width / canvas.width);
      if (height > 3000) throw new Error("A report section is too tall for a readable image. Use Export PDF.");
      if (page && cursor + height + 20 > page.height) await finish();
      if (!page) { page = document.createElement("canvas"); page.width = width; page.height = Math.max(1800, height); }
      const context = page.getContext("2d");
      if (!context) throw new Error("Image capture is unavailable.");
      context.fillStyle = "#ffffff"; context.fillRect(0, cursor, width, height + 20);
      context.drawImage(canvas, 0, cursor, width, height);
      cursor += height;
      if (cursor + 20 < page.height) cursor += 20;
    }
    await finish();
    return blobs;
  } finally { host.remove(); }
}

export async function downloadReportImages(snapshot: ReportSnapshot) {
  const blobs = await reportImages(snapshot);
  const blob = blobs.length === 1 ? blobs[0]! : new Blob([zipReportFiles(await Promise.all(blobs.map(async (image, i) => ({ name: `AskMe-report-${i + 1}.png`, bytes: new Uint8Array(await image.arrayBuffer()) })))) as BlobPart], { type: "application/zip" });
  const url = URL.createObjectURL(blob);
  download(url, blobs.length === 1 ? "AskMe-report.png" : "AskMe-report-images.zip");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
  return blobs.length;
}

export async function copyReportImage(snapshot: ReportSnapshot): Promise<void> {
  if (!navigator.clipboard?.write || typeof ClipboardItem === "undefined") throw new Error("Image clipboard is unavailable. Use Download images instead.");
  const image = reportImages(snapshot).then(blobs => {
    if (blobs.length !== 1) throw new Error("This report needs multiple images. Use Download images to preserve the entire report.");
    return blobs[0]!;
  });
  await navigator.clipboard.write([new ClipboardItem({ "image/png": image })]);
}
