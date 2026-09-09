/**
 * Copies live ASK-DB semantic YAML into public/semantic for the browser.
 * Does not modify the Python semantic engine — visualization-only mirror.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "../..");
const outRoot = path.resolve(__dirname, "../public/semantic");

const packs = [
  {
    id: "insurance",
    label: "Insurance (Postgres)",
    model: "semantic/packs/insurance/semantic_model_postgres.yaml",
    glossary: "semantic/packs/insurance/business_glossary_postgres.yaml",
  },
  {
    id: "insurance-csv",
    label: "Insurance (CSV pack)",
    model: "semantic/packs/insurance/semantic_model.yaml",
    glossary: "semantic/packs/insurance/business_glossary.yaml",
  },
  {
    id: "automotive",
    label: "Automotive Sales",
    model: "semantic/packs/automotive/semantic_model.yaml",
    glossary: "semantic/packs/automotive/business_glossary.yaml",
  },
  {
    id: "banking",
    label: "Banking",
    model: "semantic/packs/banking/semantic_model.yaml",
    glossary: "semantic/packs/banking/business_glossary.yaml",
  },
  {
    id: "healthcare",
    label: "Healthcare",
    model: "semantic/packs/healthcare/semantic_model.yaml",
    glossary: "semantic/packs/healthcare/business_glossary.yaml",
  },
  {
    id: "active",
    label: "Active live semantic/",
    model: "semantic/semantic_model.yaml",
    glossary: "semantic/business_glossary.yaml",
  },
];

fs.mkdirSync(outRoot, { recursive: true });

const manifest = [];

for (const pack of packs) {
  const destDir = path.join(outRoot, pack.id);
  fs.mkdirSync(destDir, { recursive: true });

  const modelSrc = path.join(root, pack.model);
  const glossSrc = path.join(root, pack.glossary);

  if (!fs.existsSync(modelSrc)) {
    console.warn(`[sync-yaml] skip ${pack.id}: missing ${pack.model}`);
    continue;
  }

  fs.copyFileSync(modelSrc, path.join(destDir, "semantic_model.yaml"));
  if (fs.existsSync(glossSrc)) {
    fs.copyFileSync(glossSrc, path.join(destDir, "business_glossary.yaml"));
  }

  manifest.push({
    id: pack.id,
    label: pack.label,
    modelUrl: `/semantic/${pack.id}/semantic_model.yaml`,
    glossaryUrl: fs.existsSync(glossSrc)
      ? `/semantic/${pack.id}/business_glossary.yaml`
      : null,
  });
  console.log(`[sync-yaml] ${pack.id} → public/semantic/${pack.id}`);
}

fs.writeFileSync(
  path.join(outRoot, "manifest.json"),
  JSON.stringify({ generatedAt: new Date().toISOString(), packs: manifest }, null, 2),
);
console.log(`[sync-yaml] wrote manifest (${manifest.length} packs)`);
