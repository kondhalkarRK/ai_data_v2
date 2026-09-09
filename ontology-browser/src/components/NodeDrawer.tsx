import { memo, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { OntologyNodeData } from "@/lib/types";

type TabId = "overview" | "schema" | "relationships" | "lineage";

interface NodeDrawerProps {
  node: OntologyNodeData | null;
  onClose: () => void;
}

function NodeDrawerComponent({ node, onClose }: NodeDrawerProps) {
  const [tab, setTab] = useState<TabId>("overview");

  const tabs = useMemo(
    () =>
      [
        { id: "overview" as const, label: "Overview" },
        { id: "schema" as const, label: "Schema" },
        { id: "relationships" as const, label: "Relationships" },
        { id: "lineage" as const, label: "Lineage" },
      ],
    [],
  );

  return (
    <AnimatePresence>
      {node ? (
        <motion.aside
          className="node-drawer"
          key={node.id}
          initial={{ x: 36, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 36, opacity: 0 }}
          transition={{ type: "spring", stiffness: 320, damping: 30 }}
        >
          <header className="node-drawer__header">
            <div className="node-drawer__eyebrow">
              <span
                className="dot"
                style={{ background: node.clusterColor || "#64748b" }}
              />
              {(node.cluster || node.kind).toUpperCase()}
            </div>
            <button type="button" className="icon-x" onClick={onClose} aria-label="Close">
              ×
            </button>
            <h2>{node.label}</h2>
            <p className="node-drawer__id">{node.id}</p>
          </header>

          <nav className="node-drawer__tabs" role="tablist">
            {tabs.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={tab === t.id}
                className={tab === t.id ? "is-active" : ""}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </nav>

          <div className="node-drawer__body">
            {tab === "overview" && (
              <section>
                {node.description ? <p className="lede">{node.description}</p> : null}

                <div className="section-label">Synonyms</div>
                {node.synonyms.length ? (
                  <div className="chip-row">
                    {node.synonyms.map((s) => (
                      <span key={s} className="chip">
                        {s}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="muted">None in glossary</p>
                )}

                <div className="section-label">Tables</div>
                {node.tables.length ? (
                  <div className="binding-block">
                    <div className="binding-row">
                      <strong>YAML</strong>
                      <span>{node.tables.join(", ")}</span>
                    </div>
                    {node.physicalName ? (
                      <div className="binding-row">
                        <strong>Physical</strong>
                        <span>{node.physicalName}</span>
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <p className="muted">—</p>
                )}

                <div className="section-label">Relationships</div>
                {node.relationships.length ? (
                  <ul className="plain-list">
                    {node.relationships.slice(0, 10).map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">No linked edges</p>
                )}
              </section>
            )}

            {tab === "schema" && (
              <section>
                {node.columns.length === 0 ? (
                  <p className="muted">No column schema on this node.</p>
                ) : (
                  <table className="schema-table">
                    <thead>
                      <tr>
                        <th>Attribute</th>
                        <th>Type</th>
                      </tr>
                    </thead>
                    <tbody>
                      {node.columns.map((c) => (
                        <tr key={c.name}>
                          <td>
                            <code>
                              {c.role === "key" ? "🔑 " : ""}
                              {c.name}
                            </code>
                            {c.references ? (
                              <div className="ref-line">ref:{c.references}</div>
                            ) : null}
                          </td>
                          <td>
                            {c.references ? `ref:${c.references.split(".")[0]}` : c.type}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </section>
            )}

            {tab === "relationships" && (
              <section>
                <ul className="plain-list dense">
                  {node.relationships.length ? (
                    node.relationships.map((r) => <li key={r}>{r}</li>)
                  ) : (
                    <li className="muted">No relationships</li>
                  )}
                </ul>
              </section>
            )}

            {tab === "lineage" && (
              <section>
                <ul className="plain-list dense">
                  {node.lineage.length ? (
                    node.lineage.map((l) => (
                      <li key={l}>
                        <code>{l}</code>
                      </li>
                    ))
                  ) : (
                    <li className="muted">No lineage paths</li>
                  )}
                </ul>
                {node.primaryKey ? (
                  <>
                    <div className="section-label">Primary key</div>
                    <code>{node.primaryKey}</code>
                  </>
                ) : null}
                {node.grain ? (
                  <>
                    <div className="section-label">Grain</div>
                    <p>{node.grain}</p>
                  </>
                ) : null}
              </section>
            )}
          </div>

          <footer className="node-drawer__footer">
            <span>Contracts</span>
            <span>Docs</span>
            <span>Memory</span>
            <span>Flow</span>
          </footer>
        </motion.aside>
      ) : null}
    </AnimatePresence>
  );
}

export const NodeDrawer = memo(NodeDrawerComponent);
