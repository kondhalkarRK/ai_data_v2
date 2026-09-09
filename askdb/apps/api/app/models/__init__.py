"""ORM models for the application database (``askdb_app``).

Importing this package registers every table on ``Base.metadata``, which is what Alembic
autogenerate reads. New model modules must be imported here.
"""

from app.models.activity import Conversation, LlmUsage, QueryHistory, SavedQuestion
from app.models.audit import AuthAuditEvent
from app.models.base import Base
from app.models.enums import AuthEventType, Role
from app.models.refresh_token import RefreshToken
from app.models.user import User

__all__ = [
    "AuthAuditEvent",
    "AuthEventType",
    "Base",
    "Conversation",
    "LlmUsage",
    "QueryHistory",
    "RefreshToken",
    "Role",
    "SavedQuestion",
    "User",
]
