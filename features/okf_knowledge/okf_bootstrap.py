# features/okf_knowledge/okf_bootstrap.py
#
# Seed OKF from packaged India PV business SOPs under doc/business_knowledge/.

from __future__ import annotations

from pathlib import Path

from features.okf_knowledge.md_extractor import extract_markdown_file
from features.okf_knowledge.okf_store import write_bundle, list_bundles, clear_all_bundles
from features.okf_knowledge.okf_retriever import reindex_all

# Prefer project-relative path
_DEFAULT_DOC_DIR = Path("doc") / "business_knowledge"


def business_knowledge_dir() -> Path:
    # Walk up from CWD / this file to find project root with doc/business_knowledge
    candidates = [
        Path.cwd() / _DEFAULT_DOC_DIR,
        Path(__file__).resolve().parents[2] / _DEFAULT_DOC_DIR,
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return candidates[0]


def list_packaged_sop_files() -> list[Path]:
    root = business_knowledge_dir()
    if not root.is_dir():
        return []
    files = [
        p for p in sorted(root.glob("IND-PV-*.md")) + sorted(root.glob("IND-PV-*.pdf"))
        if p.is_file()
    ]
    return files


def bootstrap_business_knowledge(force: bool = False) -> dict:
    """
    Ingest packaged SOP markdown (and PDFs if present) into OKF + Chroma.

    force=True clears existing bundles first.
    Returns summary dict: {docs, concepts, indexed, dir}.
    """
    # Prefer Markdown sources; skip PDF twin when .md exists (avoid double ingest)
    paths = list_packaged_sop_files()
    md_stems = {p.stem for p in paths if p.suffix.lower() == ".md"}
    paths = [
        p for p in paths
        if not (p.suffix.lower() == ".pdf" and p.stem in md_stems)
    ]

    if force:
        clear_all_bundles()

    # Skip if already seeded with our SOP ids (unless force)
    if not force:
        existing = list_bundles()
        already = {str(b.get("source_doc") or "") for b in existing}
        packaged_names = {p.name for p in paths}
        if packaged_names and packaged_names.issubset(already):
            return {
                "docs": len(existing),
                "concepts": 0,
                "indexed": 0,
                "dir": str(business_knowledge_dir()),
                "skipped": True,
            }

    total_concepts = 0
    docs = 0
    root = business_knowledge_dir()
    for path in paths:
        try:
            if path.suffix.lower() == ".md":
                concepts = extract_markdown_file(path)
            elif path.suffix.lower() == ".pdf":
                from features.okf_knowledge.pdf_extractor import (
                    extract_pdf_to_concepts,
                    pdf_extraction_available,
                )
                if not pdf_extraction_available():
                    continue
                concepts = extract_pdf_to_concepts(path.read_bytes(), path.name)
            else:
                continue
            if not concepts:
                continue
            if not force and any(
                b.get("source_doc") == path.name for b in list_bundles()
            ):
                continue
            write_bundle(concepts)
            total_concepts += len(concepts)
            docs += 1
        except Exception:
            continue

    indexed = reindex_all() if total_concepts or force else 0
    return {
        "docs": docs,
        "concepts": total_concepts,
        "indexed": indexed,
        "dir": str(root),
        "skipped": False,
    }
