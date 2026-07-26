# features/okf_knowledge/okf_store.py
#
# Persists OKF concept bundles to disk as small Markdown files with
# YAML frontmatter — one file per concept, one folder per source
# document. This mirrors the Open Knowledge Format convention:
# human-readable, diffable, auditable (no opaque binary blobs).
#
# New, additive module — writes only under rag_storage/okf_bundles/,
# does not touch any existing storage path.

from __future__ import annotations

import os
import re
import yaml

_STORAGE_ROOT = os.path.join("rag_storage", "okf_bundles")


def _safe_slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", text).strip("_")
    return slug[:60] or "document"


def bundle_dir_for(source_filename: str, doc_id: str) -> str:
    folder = f"{_safe_slug(source_filename)}__{doc_id}"
    return os.path.join(_STORAGE_ROOT, folder)


def write_bundle(concepts: list[dict]) -> str:
    """
    Write a list of concept dicts (from pdf_extractor.extract_pdf_to_concepts)
    to disk as individual .md files with YAML frontmatter.

    Returns the bundle directory path.
    """
    if not concepts:
        return ""

    doc_id   = concepts[0]["concept_id"].split("_")[0]
    source   = concepts[0]["source_doc"]
    out_dir  = bundle_dir_for(source, doc_id)
    os.makedirs(out_dir, exist_ok=True)

    for concept in concepts:
        frontmatter = {
            "title":       concept["title"],
            "source_doc":  concept["source_doc"],
            "source_page": concept["source_page"],
            "tags":        concept["tags"],
            "ingested_at": concept["ingested_at"],
            "concept_id":  concept["concept_id"],
        }
        fm_yaml = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)

        file_path = os.path.join(out_dir, f"{concept['concept_id']}.md")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("---\n")
            f.write(fm_yaml)
            f.write("---\n\n")
            f.write(concept["body"])

    return out_dir


def list_bundles() -> list[dict]:
    """
    List all ingested document bundles with a concept count each.
    Returns: [{"folder": ..., "source_doc": ..., "concept_count": ...}, ...]
    """
    if not os.path.isdir(_STORAGE_ROOT):
        return []

    bundles = []
    for folder in sorted(os.listdir(_STORAGE_ROOT)):
        folder_path = os.path.join(_STORAGE_ROOT, folder)
        if not os.path.isdir(folder_path):
            continue

        md_files = [f for f in os.listdir(folder_path) if f.endswith(".md")]
        if not md_files:
            continue

        source_doc = folder
        try:
            with open(os.path.join(folder_path, md_files[0]), "r", encoding="utf-8") as f:
                content = f.read()
            if content.startswith("---"):
                fm_text = content.split("---", 2)[1]
                fm = yaml.safe_load(fm_text) or {}
                source_doc = fm.get("source_doc", source_doc)
        except Exception:
            pass

        bundles.append({
            "folder": folder,
            "source_doc": source_doc,
            "concept_count": len(md_files),
        })

    return bundles


def read_all_concepts() -> list[dict]:
    """
    Read every concept .md file across all bundles back into memory,
    for (re)indexing by okf_retriever.py.

    Returns list of dicts: {concept_id, title, source_doc, source_page,
    tags, body}.
    """
    if not os.path.isdir(_STORAGE_ROOT):
        return []

    concepts = []
    for folder in os.listdir(_STORAGE_ROOT):
        folder_path = os.path.join(_STORAGE_ROOT, folder)
        if not os.path.isdir(folder_path):
            continue

        for fname in os.listdir(folder_path):
            if not fname.endswith(".md"):
                continue
            try:
                with open(os.path.join(folder_path, fname), "r", encoding="utf-8") as f:
                    content = f.read()
                if not content.startswith("---"):
                    continue
                _, fm_text, body = content.split("---", 2)
                fm = yaml.safe_load(fm_text) or {}
                concepts.append({
                    "concept_id":  fm.get("concept_id", fname),
                    "title":       fm.get("title", fname),
                    "source_doc":  fm.get("source_doc", ""),
                    "source_page": fm.get("source_page", ""),
                    "tags":        fm.get("tags", []),
                    "body":        body.strip(),
                })
            except Exception:
                continue

    return concepts


def clear_all_bundles() -> int:
    """Delete all stored OKF bundles. Returns count of folders removed."""
    import shutil

    if not os.path.isdir(_STORAGE_ROOT):
        return 0

    removed = 0
    for folder in os.listdir(_STORAGE_ROOT):
        folder_path = os.path.join(_STORAGE_ROOT, folder)
        if os.path.isdir(folder_path):
            shutil.rmtree(folder_path, ignore_errors=True)
            removed += 1

    return removed
