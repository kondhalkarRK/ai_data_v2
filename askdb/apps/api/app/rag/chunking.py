"""Intelligent-ish chunking with page/section provenance for Traditional RAG."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TextChunk:
    ordinal: int
    text: str
    locator: str


_HEADING = re.compile(r"^(#{1,6}\s+.+|[A-Z][A-Za-z0-9 ,/&\-]{0,80}$)")
_PAGE_BREAK = re.compile(r"\f|\n\s*---\s*page\s+(\d+)\s*---\s*\n", re.IGNORECASE)


def chunk_document_text(
    text: str,
    *,
    max_chars: int,
    min_chars: int,
    overlap: int,
) -> list[TextChunk]:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return []

    pages = _split_pages(cleaned)
    pieces: list[tuple[str, str]] = []
    for page_no, page_text in pages:
        section = "body"
        for block in _split_sections(page_text):
            heading, body = block
            if heading:
                section = heading.strip()[:80]
            body = re.sub(r"[ \t]+", " ", body).strip()
            if not body:
                continue
            for part in _window(body, max_chars=max_chars, min_chars=min_chars, overlap=overlap):
                locator = f"page-{page_no}/section-{_slug(section)}/chunk"
                pieces.append((part, locator))

    chunks: list[TextChunk] = []
    for index, (part, locator_base) in enumerate(pieces):
        chunks.append(
            TextChunk(
                ordinal=index,
                text=part,
                locator=f"{locator_base}-{index + 1}",
            )
        )
    if not chunks and cleaned:
        for index, part in enumerate(
            _window(cleaned, max_chars=max_chars, min_chars=min_chars, overlap=overlap)
        ):
            chunks.append(
                TextChunk(ordinal=index, text=part, locator=f"chunk-{index + 1}")
            )
    return chunks


def _split_pages(text: str) -> list[tuple[int, str]]:
    if "\f" in text:
        parts = text.split("\f")
        return [(i + 1, part) for i, part in enumerate(parts) if part.strip()]
    matches = list(_PAGE_BREAK.finditer(text))
    if not matches:
        return [(1, text)]
    pages: list[tuple[int, str]] = []
    cursor = 0
    page_no = 1
    for match in matches:
        chunk = text[cursor : match.start()]
        if chunk.strip():
            pages.append((page_no, chunk))
        page_no = int(match.group(1) or page_no + 1)
        cursor = match.end()
    tail = text[cursor:]
    if tail.strip():
        pages.append((page_no, tail))
    return pages or [(1, text)]


def _split_sections(text: str) -> list[tuple[str | None, str]]:
    lines = text.split("\n")
    blocks: list[tuple[str | None, str]] = []
    current_heading: str | None = None
    buf: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and _HEADING.match(stripped) and len(stripped) < 100:
            if buf:
                blocks.append((current_heading, "\n".join(buf)))
                buf = []
            current_heading = stripped.lstrip("#").strip()
            continue
        buf.append(line)
    if buf:
        blocks.append((current_heading, "\n".join(buf)))
    return blocks or [(None, text)]


def _window(text: str, *, max_chars: int, min_chars: int, overlap: int) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [cleaned]
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + max_chars)
        if end < len(cleaned):
            split_at = cleaned.rfind(". ", start, end)
            if split_at > start + min_chars:
                end = split_at + 1
        piece = cleaned[start:end].strip()
        if len(piece) >= min_chars or end >= len(cleaned):
            chunks.append(piece)
        if end >= len(cleaned):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug[:48] or "body"
