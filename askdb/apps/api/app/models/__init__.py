"""ORM models for the application database (``askdb_app``).

Importing this package registers every table on ``Base.metadata``, which is what Alembic
autogenerate reads. New model modules must be imported here.
"""

from app.models.activity import Conversation, LlmUsage, QueryHistory, SavedAnalysis, SavedQuestion
from app.models.audit import AuthAuditEvent
from app.models.base import Base
from app.models.catalog import CatalogChange, CatalogColumn, CatalogRefresh, CatalogValue
from app.models.enums import AuthEventType, ExecutionMode, Role
from app.models.governance import AdminAudit, AppSetting, LoginAudit
from app.models.refresh_token import RefreshToken
from app.models.region_access import UserRegionAccess
from app.models.reliability import DqRuleRun, DqRuleSetting, DqScoreSnapshot
from app.models.user import User

__all__ = [
    "AdminAudit",
    "AppSetting",
    "AuthAuditEvent",
    "AuthEventType",
    "Base",
    "CatalogChange",
    "CatalogColumn",
    "CatalogRefresh",
    "CatalogValue",
    "Conversation",
    "DqRuleRun",
    "DqRuleSetting",
    "DqScoreSnapshot",
    "ExecutionMode",
    "LlmUsage",
    "LoginAudit",
    "QueryHistory",
    "RefreshToken",
    "Role",
    "SavedAnalysis",
    "SavedQuestion",
    "User",
    "UserRegionAccess",
]
