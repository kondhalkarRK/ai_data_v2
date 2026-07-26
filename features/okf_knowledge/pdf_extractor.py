# features/okf_knowledge/pdf_extractor.py
#
# Converts an uploaded business PDF into an "Open Knowledge Format"
# (OKF) style bundle: a folder of small Markdown files, each with a
# short YAML frontmatter header, one file per concept/section.
#
# Design goal: ZERO LLM tokens spent at ingestion time. This is pure
# text extraction + heuristic chunking — no model call. Token cost
# only ever happens later, per question, and only for the 2-4 small
# concept snippets retrieval picks out (see okf_retriever.py).
#
# This is a new, additive module. It does not import or modify any
# existing engine file.

from __future__ import annotations

import io
import re
import uuid
from datetime import datetime, timezone

try:
    from pypdf import PdfReader
    _PDF_AVAILABLE = True
except ImportError:
    _PDF_AVAILABLE = False

_MAX_CONCEPT_CHARS = 1400   # keeps each concept file small -> low token cost per retrieval hit
_MIN_CONCEPT_CHARS = 40     # skip near-empty fragments (e.g. blank pages)


def pdf_extraction_available() -> bool:
    return _PDF_AVAILABLE


def _clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _guess_title(chunk_text: str, fallback: str) -> str:
    """Heuristic title: first short, non-empty line of the chunk."""
    for line in chunk_text.splitlines():
        line = line.strip()
        if 3 <= len(line) <= 90:
            return line
    return fallback


def _split_page_into_concepts(page_text: str) -> list[str]:
    """
    Split a page's text into concept-sized chunks on blank-line
    paragraph boundaries, merging short paragraphs together up to
    _MAX_CONCEPT_CHARS so each concept stays compact but coherent.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", page_text) if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if not current:
            current = para
        elif len(current) + len(para) + 2 <= _MAX_CONCEPT_CHARS:
            current += "\n\n" + para
        else:
            chunks.append(current)
            current = para

    if current:
        chunks.append(current)

    # Hard-cap any single oversized paragraph
    final_chunks = []
    for c in chunks:
        if len(c) <= _MAX_CONCEPT_CHARS:
            final_chunks.append(c)
        else:
            for i in range(0, len(c), _MAX_CONCEPT_CHARS):
                final_chunks.append(c[i:i + _MAX_CONCEPT_CHARS])

    return final_chunks


def extract_pdf_to_concepts(file_bytes: bytes, source_filename: str) -> list[dict]:
    """
    Extract a PDF into a list of OKF "concept" dicts, ready to be
    written to disk by okf_store.py and indexed by okf_retriever.py.

    Each concept dict:
        {
            "concept_id":   unique id
            "title":        short heuristic title
            "source_doc":   original filename
            "source_page":  1-indexed page number
            "tags":         list[str]
            "body":         concept text (<= _MAX_CONCEPT_CHARS chars)
            "ingested_at":  ISO timestamp
        }

    Pure extraction — no LLM call is made here.
    """
    if not _PDF_AVAILABLE:
        raise RuntimeError(
            "pypdf is not installed. Install it with: "
            "pip install pypdf --break-system-packages"
        )

    reader = PdfReader(io.BytesIO(file_bytes))
    doc_id = str(uuid.uuid4())[:8]
    now    = datetime.now(timezone.utc).isoformat()

    concepts: list[dict] = []

    for page_idx, page in enumerate(reader.pages, start=1):
        try:
            raw_text = page.extract_text() or ""
        except Exception:
            raw_text = ""

        cleaned = _clean_text(raw_text)
        if len(cleaned) < _MIN_CONCEPT_CHARS:
            continue

        for chunk in _split_page_into_concepts(cleaned):
            if len(chunk) < _MIN_CONCEPT_CHARS:
                continue

            title = _guess_title(chunk, fallback=f"{source_filename} — page {page_idx}")

            concepts.append({
                "concept_id":  f"{doc_id}_{page_idx}_{len(concepts)}",
                "title":       title,
                "source_doc":  source_filename,
                "source_page": page_idx,
                "tags":        ["pdf", "business-doc"],
                "body":        chunk,
                "ingested_at": now,
            })

    return concepts
