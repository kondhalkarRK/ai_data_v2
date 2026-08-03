# features/okf_knowledge/md_extractor.py
#
# Convert Markdown business SOPs into OKF concept dicts (same shape as
# pdf_extractor) using heading-based chunking — zero LLM cost.

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

_MAX_CONCEPT_CHARS = 1400
_MIN_CONCEPT_CHARS = 40


def _clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_oversized(body: str) -> list[str]:
    if len(body) <= _MAX_CONCEPT_CHARS:
        return [body]
    parts: list[str] = []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    current = ""
    for para in paragraphs:
        if not current:
            current = para
        elif len(current) + len(para) + 2 <= _MAX_CONCEPT_CHARS:
            current += "\n\n" + para
        else:
            parts.append(current)
            current = para
    if current:
        parts.append(current)
    final: list[str] = []
    for c in parts:
        if len(c) <= _MAX_CONCEPT_CHARS:
            final.append(c)
        else:
            for i in range(0, len(c), _MAX_CONCEPT_CHARS):
                final.append(c[i:i + _MAX_CONCEPT_CHARS])
    return final


def extract_markdown_to_concepts(
    text: str,
    source_filename: str,
    default_tags: list[str] | None = None,
) -> list[dict]:
    """
    Split Markdown on AT2 headings into OKF concepts.
    Falls back to paragraph chunking when no headings exist.
    """
    text = _clean_text(text or "")
    if len(text) < _MIN_CONCEPT_CHARS:
        return []

    doc_id = str(uuid.uuid4())[:8]
    now = datetime.now(timezone.utc).isoformat()
    tags = list(default_tags or ["markdown", "business-doc", "sop"])

    # Detect document id from first heading / filename
    doc_tag = None
    m = re.search(r"\b(IND-PV-(?:SOP|GUIDE)-\d{3})\b", text)
    if m:
        doc_tag = m.group(1)
        tags.append(doc_tag.lower())

    sections: list[tuple[str, str]] = []
    # Split on ## headings (keep title)
    parts = re.split(r"(?m)^(#{1,3})\s+(.+)$", text)
    # parts: [preamble, level, title, body, level, title, body, ...]
    if len(parts) >= 4:
        preamble = parts[0].strip()
        if len(preamble) >= _MIN_CONCEPT_CHARS:
            sections.append((f"{source_filename} — overview", preamble))
        i = 1
        while i + 2 < len(parts):
            title = parts[i + 1].strip()
            body = parts[i + 2].strip()
            # Skip pure metadata one-liners
            if len(body) >= _MIN_CONCEPT_CHARS:
                sections.append((title, body))
            i += 3
    else:
        sections.append((source_filename, text))

    concepts: list[dict] = []
    page_proxy = 1
    for title, body in sections:
        for chunk in _split_oversized(body):
            if len(chunk) < _MIN_CONCEPT_CHARS:
                continue
            # Prefix title into body for better embedding match
            full_body = f"{title}\n\n{chunk}" if not chunk.startswith(title) else chunk
            if len(full_body) > _MAX_CONCEPT_CHARS:
                full_body = full_body[:_MAX_CONCEPT_CHARS]
            concept_tags = list(tags)
            low = (title + " " + chunk).lower()
            if any(w in low for w in ("covid", "lockdown", "recovery")):
                concept_tags.append("covid")
            if any(w in low for w in ("ev", "electric", "powertrain", "battery")):
                concept_tags.append("ev")
            if any(w in low for w in ("region", "territory", "metro", "zone")):
                concept_tags.append("region")
            if any(w in low for w in ("metric", "kpi", "revenue", "units")):
                concept_tags.append("metrics")
            if any(w in low for w in ("narrative", "executive", "insight")):
                concept_tags.append("narrative")

            concepts.append({
                "concept_id": f"{doc_id}_{page_proxy}_{len(concepts)}",
                "title": title[:90],
                "source_doc": source_filename,
                "source_page": page_proxy,
                "tags": concept_tags,
                "body": full_body,
                "ingested_at": now,
                "doc_code": doc_tag or "",
            })
        page_proxy += 1

    return concepts


def extract_markdown_file(path: str | Path) -> list[dict]:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    return extract_markdown_to_concepts(text, p.name)
