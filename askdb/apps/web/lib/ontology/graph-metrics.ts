/** Graph metrics for ontology centrality modes. */

export type GraphLink = { source: string; target: string };

export function adjacency(
  nodeIds: string[],
  links: GraphLink[],
): Map<string, Set<string>> {
  const adj = new Map<string, Set<string>>();
  for (const id of nodeIds) adj.set(id, new Set());
  for (const link of links) {
    adj.get(link.source)?.add(link.target);
    adj.get(link.target)?.add(link.source);
  }
  return adj;
}

export function degreeCentrality(nodeIds: string[], links: GraphLink[]): Map<string, number> {
  const scores = new Map<string, number>();
  for (const id of nodeIds) scores.set(id, 0);
  for (const link of links) {
    scores.set(link.source, (scores.get(link.source) ?? 0) + 1);
    scores.set(link.target, (scores.get(link.target) ?? 0) + 1);
  }
  const max = Math.max(1, ...scores.values());
  for (const [id, value] of scores) scores.set(id, value / max);
  return scores;
}

/** Brandes betweenness centrality, normalized to [0, 1]. */
export function betweennessCentrality(
  nodeIds: string[],
  links: GraphLink[],
): Map<string, number> {
  const adj = adjacency(nodeIds, links);
  const scores = new Map<string, number>();
  for (const id of nodeIds) scores.set(id, 0);

  for (const source of nodeIds) {
    const stack: string[] = [];
    const predecessors = new Map<string, string[]>();
    const sigma = new Map<string, number>();
    const dist = new Map<string, number>();
    const delta = new Map<string, number>();

    for (const id of nodeIds) {
      predecessors.set(id, []);
      sigma.set(id, 0);
      dist.set(id, -1);
      delta.set(id, 0);
    }
    sigma.set(source, 1);
    dist.set(source, 0);

    const queue = [source];
    while (queue.length) {
      const v = queue.shift()!;
      stack.push(v);
      for (const w of adj.get(v) ?? []) {
        if ((dist.get(w) ?? -1) < 0) {
          dist.set(w, (dist.get(v) ?? 0) + 1);
          queue.push(w);
        }
        if (dist.get(w) === (dist.get(v) ?? 0) + 1) {
          sigma.set(w, (sigma.get(w) ?? 0) + (sigma.get(v) ?? 0));
          predecessors.get(w)?.push(v);
        }
      }
    }

    while (stack.length) {
      const w = stack.pop()!;
      for (const v of predecessors.get(w) ?? []) {
        const share =
          ((sigma.get(v) ?? 0) / Math.max(1, sigma.get(w) ?? 1)) * (1 + (delta.get(w) ?? 0));
        delta.set(v, (delta.get(v) ?? 0) + share);
      }
      if (w !== source) scores.set(w, (scores.get(w) ?? 0) + (delta.get(w) ?? 0));
    }
  }

  const n = nodeIds.length;
  const norm = n > 2 ? (n - 1) * (n - 2) : 1;
  const max = Math.max(1, ...[...scores.values()].map((v) => v / norm));
  for (const [id, value] of scores) scores.set(id, value / norm / max);
  return scores;
}

/** Power-iteration PageRank, normalized to [0, 1]. */
export function pageRank(
  nodeIds: string[],
  links: GraphLink[],
  damping = 0.85,
  iterations = 40,
): Map<string, number> {
  const n = nodeIds.length;
  if (n === 0) return new Map();
  const adj = adjacency(nodeIds, links);
  const outDegree = new Map<string, number>();
  for (const id of nodeIds) outDegree.set(id, adj.get(id)?.size ?? 0);

  let ranks = new Map<string, number>();
  for (const id of nodeIds) ranks.set(id, 1 / n);

  for (let i = 0; i < iterations; i += 1) {
    const next = new Map<string, number>();
    const base = (1 - damping) / n;
    for (const id of nodeIds) next.set(id, base);
    for (const id of nodeIds) {
      const neighbors = [...(adj.get(id) ?? [])];
      const share =
        neighbors.length === 0
          ? (damping * (ranks.get(id) ?? 0)) / n
          : (damping * (ranks.get(id) ?? 0)) / neighbors.length;
      if (neighbors.length === 0) {
        for (const target of nodeIds) next.set(target, (next.get(target) ?? 0) + share);
      } else {
        for (const target of neighbors) next.set(target, (next.get(target) ?? 0) + share);
      }
    }
    ranks = next;
  }

  const max = Math.max(1e-9, ...ranks.values());
  for (const [id, value] of ranks) ranks.set(id, value / max);
  return ranks;
}

export function hopNeighborhood(
  rootId: string,
  links: Array<GraphLink & { id?: string }>,
  hops: number,
): { nodes: Set<string>; edges: Set<string> } {
  const undirected = new Map<string, Array<{ id: string; edgeId: string }>>();
  for (const link of links) {
    const edgeId = link.id ?? `${link.source}->${link.target}`;
    if (!undirected.has(link.source)) undirected.set(link.source, []);
    if (!undirected.has(link.target)) undirected.set(link.target, []);
    undirected.get(link.source)!.push({ id: link.target, edgeId });
    undirected.get(link.target)!.push({ id: link.source, edgeId });
  }

  const nodes = new Set<string>([rootId]);
  const edges = new Set<string>();
  let frontier = new Set<string>([rootId]);

  for (let depth = 0; depth < hops; depth += 1) {
    const next = new Set<string>();
    for (const node of frontier) {
      for (const neighbor of undirected.get(node) ?? []) {
        edges.add(neighbor.edgeId);
        if (!nodes.has(neighbor.id)) {
          nodes.add(neighbor.id);
          next.add(neighbor.id);
        }
      }
    }
    frontier = next;
  }
  return { nodes, edges };
}
