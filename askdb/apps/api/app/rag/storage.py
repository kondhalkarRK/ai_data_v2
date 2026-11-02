"""Private original-file storage for Traditional RAG (local now, Azure later)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.core.config import APP_ROOT, Industry, Settings
from app.core.exceptions import ValidationError

# MVP formats only (CSV/PPTX excluded).
ALLOWED_EXTENSIONS = frozenset({".pdf", ".docx", ".txt", ".md", ".html"})
MIME_BY_EXT = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".html": "text/html",
}
# Magic-byte / content sniffing helpers (lightweight, not full libmagic).
_PDF_MAGIC = b"%PDF"
_ZIP_MAGIC = b"PK"  # DOCX is a ZIP package
_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._\- ()]+")


@dataclass(frozen=True, slots=True)
class StoredOriginal:
    storage_key: str
    absolute_path: Path
    content_type: str
    extension: str
    safe_filename: str
    byte_size: int


def sanitize_filename(filename: str) -> str:
    raw = (filename or "").strip()
    if not raw or "\x00" in raw:
        raise ValidationError("Invalid filename.")
    normalized = raw.replace("\\", "/")
    if ".." in normalized.split("/"):
        raise ValidationError("Path traversal is not allowed in filenames.")
    if normalized.startswith("/") or ":/" in normalized[:3].replace("\\", "/"):
        raise ValidationError("Path traversal is not allowed in filenames.")
    name = Path(normalized).name.strip()
    if not name or name in {".", ".."}:
        raise ValidationError("Invalid filename.")
    if "/" in name or "\\" in name:
        raise ValidationError("Path traversal is not allowed in filenames.")
    cleaned = _UNSAFE_NAME.sub("_", name).strip(" ._")
    if not cleaned:
        raise ValidationError("Invalid filename.")
    return cleaned[:200]


def detect_extension_and_mime(
    *, filename: str, raw: bytes, declared_content_type: str | None = None
) -> tuple[str, str]:
    safe = sanitize_filename(filename)
    ext = Path(safe).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(f"Unsupported upload type '{ext or '(none)'}'.")
    expected_mime = MIME_BY_EXT[ext]
    declared = (declared_content_type or "").split(";")[0].strip().lower()
    if declared and declared not in {"application/octet-stream", "binary/octet-stream"}:
        if ext == ".md" and declared in {"text/plain", "text/markdown"}:
            pass
        elif ext == ".html" and declared in {"text/html", "application/xhtml+xml"}:
            pass
        elif declared != expected_mime:
            raise ValidationError(
                f"MIME type '{declared}' does not match extension '{ext}'."
            )
    if ext == ".pdf" and not raw.startswith(_PDF_MAGIC):
        raise ValidationError("File content is not a valid PDF.")
    if ext == ".docx" and not raw.startswith(_ZIP_MAGIC):
        raise ValidationError("File content is not a valid DOCX package.")
    if ext in {".txt", ".md", ".html"}:
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationError(f"{ext} files must use UTF-8 encoding.") from exc
    return ext, expected_mime


class DocumentBlobStore:
    """Server-generated paths under ``data/knowledge/{industry}/files/{doc_id}/``."""

    def __init__(self, settings: Settings, industry: Industry) -> None:
        self.settings = settings
        self.industry = industry
        root = (
            Path(settings.rag_storage_root)
            if settings.rag_storage_root
            else APP_ROOT / "data" / "knowledge"
        )
        self.root = root / industry.value / "files"
        self.root.mkdir(parents=True, exist_ok=True)

    def storage_key_for(self, document_id: uuid.UUID, extension: str) -> str:
        return f"{self.industry.value}/files/{document_id}/original{extension}"

    def absolute_path(self, storage_key: str) -> Path:
        if ".." in storage_key.replace("\\", "/").split("/"):
            raise ValidationError("Invalid storage key.")
        path = (self.root.parent.parent / storage_key).resolve()
        base = self.root.parent.parent.resolve()
        if not str(path).startswith(str(base)):
            raise ValidationError("Invalid storage key.")
        return path

    def write_original(
        self,
        *,
        document_id: uuid.UUID,
        filename: str,
        raw: bytes,
        declared_content_type: str | None = None,
    ) -> StoredOriginal:
        if self.settings.rag_storage_backend != "local":
            raise ValidationError(
                "Only the local storage backend is implemented for this POC."
            )
        if len(raw) > self.settings.upload_max_bytes:
            raise ValidationError("Upload exceeds the configured size limit.")
        if len(raw) == 0:
            raise ValidationError("Empty uploads are not allowed.")
        safe_name = sanitize_filename(filename)
        ext, content_type = detect_extension_and_mime(
            filename=safe_name, raw=raw, declared_content_type=declared_content_type
        )
        key = self.storage_key_for(document_id, ext)
        path = self.absolute_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise ValidationError("Original file already exists for this document version.")
        path.write_bytes(raw)
        return StoredOriginal(
            storage_key=key,
            absolute_path=path,
            content_type=content_type,
            extension=ext,
            safe_filename=safe_name,
            byte_size=len(raw),
        )

    def read_bytes(self, storage_key: str) -> bytes:
        path = self.absolute_path(storage_key)
        if not path.is_file():
            raise ValidationError("Original file is missing.")
        return path.read_bytes()

    def write_extracted_text(self, document_id: uuid.UUID, text: str) -> Path:
        path = self.root.parent / "extracted" / f"{document_id}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path
