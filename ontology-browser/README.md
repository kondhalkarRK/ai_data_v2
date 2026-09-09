# ASK-DB Ontology Browser

Visualization-only React app. Reads existing YAML semantic models — does **not** modify the Python semantic engine.

## Stack

- React + TypeScript
- React Flow (`@xyflow/react`)
- Framer Motion
- js-yaml parser
- d3-force (Force / Centrality) + dagre (Hierarchy)

## Run

```bash
cd ontology-browser
npm install
npm run dev
```

Open http://localhost:5173

YAML packs are mirrored from `../semantic/**` into `public/semantic/` via `npm run sync-yaml` (runs automatically on `dev` / `build`).

## Layout modes

- **Force** — physics layout, draggable nodes
- **Centrality** — degree-weighted sizing + stronger clustering
- **Hierarchy** — parent/child dagre tree

## Production build

```bash
npm run build
npm run preview
```
