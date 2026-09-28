export type Point = { x: number; y: number };

export type CurveGeometry = {
  start: Point;
  control: Point;
  end: Point;
  path: string;
};

/**
 * Quadratic curve between two circles, trimmed to each circle's rim so arrowheads sit
 * on the node edge instead of under the label.
 */
export function curveBetween(
  sourceCenter: Point,
  targetCenter: Point,
  sourceRadius: number,
  targetRadius: number,
  curvature: number,
): CurveGeometry {
  const dx = targetCenter.x - sourceCenter.x;
  const dy = targetCenter.y - sourceCenter.y;
  const dist = Math.max(1, Math.hypot(dx, dy));
  const mid = { x: (sourceCenter.x + targetCenter.x) / 2, y: (sourceCenter.y + targetCenter.y) / 2 };
  const normal = { x: -dy / dist, y: dx / dist };
  const control = {
    x: mid.x + normal.x * dist * curvature,
    y: mid.y + normal.y * dist * curvature,
  };
  const start = towards(sourceCenter, control, sourceRadius);
  const end = towards(targetCenter, control, targetRadius);
  return {
    start,
    control,
    end,
    path: `M ${start.x} ${start.y} Q ${control.x} ${control.y} ${end.x} ${end.y}`,
  };
}

function towards(from: Point, to: Point, distance: number): Point {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const len = Math.max(1, Math.hypot(dx, dy));
  return { x: from.x + (dx / len) * distance, y: from.y + (dy / len) * distance };
}

export function pointOnCurve(curve: CurveGeometry, t: number): Point {
  const u = 1 - t;
  return {
    x: u * u * curve.start.x + 2 * u * t * curve.control.x + t * t * curve.end.x,
    y: u * u * curve.start.y + 2 * u * t * curve.control.y + t * t * curve.end.y,
  };
}

export function labelBox(text: string, center: Point) {
  const width = text.length * 6 + 18;
  const height = 18;
  return { x: center.x - width / 2, y: center.y - height / 2, width, height };
}

type Box = ReturnType<typeof labelBox>;

function overlapArea(a: Box, b: Box): number {
  const w = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
  const h = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
  return w > 0 && h > 0 ? w * h : 0;
}

export type LabelPlacementInput = {
  id: string;
  label: string;
  source: Point;
  target: Point;
  sourceRadius: number;
  targetRadius: number;
  curvature: number;
};

export type LabelPlacement = { curvature: number; labelT: number };

const T_CANDIDATES = [0.5, 0.4, 0.6, 0.32, 0.68, 0.25, 0.75];

/**
 * Greedy label placement: try positions along each curve (and the mirrored curve) and
 * keep the first spot that does not sit on another label or on a node and its caption.
 */
export function placeEdgeLabels(
  edges: LabelPlacementInput[],
  obstacles: Box[],
): Map<string, LabelPlacement> {
  const placed: Box[] = [];
  const result = new Map<string, LabelPlacement>();
  for (const edge of edges) {
    let best: { score: number; placement: LabelPlacement; box: Box } | null = null;
    search: for (const curvature of [edge.curvature, -edge.curvature]) {
      const curve = curveBetween(edge.source, edge.target, edge.sourceRadius, edge.targetRadius, curvature);
      for (const t of T_CANDIDATES) {
        const box = labelBox(edge.label, pointOnCurve(curve, t));
        let overlap = 0;
        for (const other of placed) overlap += overlapArea(box, other) * 3;
        for (const other of obstacles) overlap += overlapArea(box, other);
        const score = overlap + Math.abs(t - 0.5) * 40 + (curvature === edge.curvature ? 0 : 20);
        if (!best || score < best.score) best = { score, placement: { curvature, labelT: t }, box };
        if (overlap === 0) break search;
      }
    }
    if (best) {
      placed.push(best.box);
      result.set(edge.id, best.placement);
    }
  }
  return result;
}
