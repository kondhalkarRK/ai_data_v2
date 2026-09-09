import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import OntologyBrowser from "@/components/OntologyBrowser";
import { loadPackGraph } from "@/lib/yamlParser";
import type { OntologyGraph, PackManifest } from "@/lib/types";

export default function GraphPage() {
  const { packId } = useParams();
  const navigate = useNavigate();
  const [manifest, setManifest] = useState<PackManifest | null>(null);
  const [graph, setGraph] = useState<OntologyGraph | null>(null);
  const [buildMs, setBuildMs] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const selectedPackId = packId || "active";

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/semantic/manifest.json");
        if (!res.ok) throw new Error("manifest.json missing — run npm run sync-yaml");
        const data = (await res.json()) as PackManifest;
        if (!cancelled) setManifest(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const pack = useMemo(() => {
    if (!manifest) return null;
    return (
      manifest.packs.find((p) => p.id === selectedPackId) ||
      manifest.packs.find((p) => p.id === "active") ||
      manifest.packs[0] ||
      null
    );
  }, [manifest, selectedPackId]);

  useEffect(() => {
    if (!pack) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      const t0 = performance.now();
      try {
        const g = await loadPackGraph(pack.modelUrl, pack.glossaryUrl);
        if (cancelled) return;
        setGraph(g);
        setBuildMs(Math.round(performance.now() - t0));
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pack]);

  return (
    <div className="app-frame">
      <header className="app-topbar">
        <div className="brand">
          <strong>ASK-DB</strong>
          <span>Ontology Browser</span>
        </div>
        <div className="pack-select">
          <label htmlFor="pack">Domain pack</label>
          <select
            id="pack"
            value={pack?.id || selectedPackId}
            onChange={(e) => navigate(`/graph/${e.target.value}`)}
          >
            {(manifest?.packs || []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
        <div className="top-actions">
          <Link to="/" className="ghost-link">
            Home
          </Link>
          <span className="live-badge">Live YAML</span>
        </div>
      </header>

      {error ? <div className="banner error">{error}</div> : null}
      {loading || !graph ? (
        <div className="banner">Loading semantic YAML…</div>
      ) : (
        <OntologyBrowser
          graph={graph}
          buildMs={buildMs}
          packLabel={pack?.label || "bundled ontology snapshot"}
        />
      )}
    </div>
  );
}
