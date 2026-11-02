"""Ask Me RAG feature flag (Phase 0+).

When disabled, mutating document APIs are blocked and chat/Hub keep legacy behaviour.
Later phases gate Qdrant retrieval and grounded generation on the same flag.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.exceptions import RagDisabledError


def rag_enabled(settings: Settings) -> bool:
    return bool(settings.ask_me_rag_enabled)


def require_rag_mutations(settings: Settings) -> None:
    """Raise when upload, replace, reindex or delete must not run."""
    if not rag_enabled(settings):
        raise RagDisabledError()
