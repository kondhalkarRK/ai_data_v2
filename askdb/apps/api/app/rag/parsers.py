"""Safe text extraction for supported knowledge document formats."""

from __future__ import annotations

import io
import re
from pathlib import Path

from app.core.exceptions import ValidationError


def extract_text(filename: str, raw: bytes) -> str:
    """Extract plain text from an uploaded document."""
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md"}:
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationError(f"{suffix} files must use UTF-8 encoding.") from exc
    if suffix == ".html":
        try:
            html = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationError(".html files must use UTF-8 encoding.") from exc
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ValidationError(
                "PDF support requires the optional 'pypdf' dependency."
            ) from exc
        try:
            return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages)
        except Exception as exc:
            raise ValidationError("The PDF could not be parsed.") from exc
    if suffix == ".docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise ValidationError(
                "DOCX support requires the optional 'python-docx' dependency."
            ) from exc
        try:
            return "\n".join(paragraph.text for paragraph in Document(io.BytesIO(raw)).paragraphs)
        except Exception as exc:
            raise ValidationError("The DOCX file could not be parsed.") from exc
    raise ValidationError(f"Unsupported upload type '{suffix or '(none)'}'.")
