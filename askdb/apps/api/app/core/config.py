"""Application settings.

Every value comes from the environment. This module is the single replacement for the
legacy ``config/settings.py``, which read Streamlit secrets first and then fell back to
environment variables.
"""

from __future__ import annotations

import secrets
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

APP_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = APP_ROOT.parents[1]


class Environment(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Industry(StrEnum):
    """The two supported analytics industries.

    Adding an industry means adding a semantic pack, a database URL and a member here.
    """

    AUTOMOTIVE = "automotive"
    INSURANCE = "insurance"


# NoDecode stops pydantic-settings from attempting to JSON-parse the raw environment
# value, so `_parse_csv` below receives the comma-separated string the .env file holds.
CsvList = Annotated[list[str], NoDecode, Field(default_factory=list)]


def _split_csv(value: object) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", APP_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- runtime -----------------------------------------------------------
    environment: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"  # noqa: S104 - bound inside a container, not on a host
    api_port: int = 8000
    app_name: str = "NQL Insight"
    api_v1_prefix: str = "/api/v1"

    # --- security ----------------------------------------------------------
    jwt_secret_key: SecretStr = SecretStr("")
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_access_ttl_minutes: int = Field(default=15, ge=1, le=120)
    jwt_refresh_ttl_days: int = Field(default=14, ge=1, le=90)
    jwt_issuer: str = "nql-insight"
    jwt_audience: str = "nql-insight-web"

    cookie_domain: str = "localhost"
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    csrf_header_name: str = "x-csrf-token"

    cors_allowed_origins: CsvList
    trusted_hosts: CsvList

    rate_limit_login_per_minute: int = Field(default=5, ge=1)
    rate_limit_api_per_minute: int = Field(default=120, ge=1)

    # TEMPORARY local testing only. When true, API routes skip JWT/CSRF and act as the
    # first active admin. Refused in production. Pair with NEXT_PUBLIC_AUTH_BYPASS on web.
    auth_bypass: bool = False

    # --- databases ---------------------------------------------------------
    app_database_url: str = "postgresql+psycopg://askdb_app:askdb_app@localhost:5432/askdb_app"
    # Runtime analytics URLs must stay SELECT-only (askdb_reader).
    automotive_database_url: str = (
        "postgresql+psycopg://askdb_reader:askdb_reader@localhost:5432/askdb_automotive"
    )
    insurance_database_url: str = (
        "postgresql+psycopg://askdb_reader:askdb_reader@localhost:5432/askdb_insurance"
    )
    # Migration/seed URLs use askdb_owner so the reader never needs DDL/DML rights.
    automotive_migrate_database_url: str = (
        "postgresql+psycopg://askdb_owner:askdb_owner@localhost:5432/askdb_automotive"
    )
    insurance_migrate_database_url: str = (
        "postgresql+psycopg://askdb_owner:askdb_owner@localhost:5432/askdb_insurance"
    )
    default_industry: Industry = Industry.INSURANCE

    db_pool_min_size: int = Field(default=1, ge=0)
    db_pool_max_size: int = Field(default=10, ge=1)
    db_connect_timeout_seconds: int = Field(default=10, ge=1)
    sql_statement_timeout_seconds: int = Field(default=30, ge=1, le=300)
    sql_max_result_rows: int = Field(default=1000, ge=1, le=100_000)
    sql_preview_page_size: int = Field(default=50, ge=1, le=500)

    # --- mongo / qdrant ----------------------------------------------------
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "nql_insight"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr = SecretStr("")
    qdrant_vector_size: int = 384

    # --- embeddings / llm --------------------------------------------------
    embeddings_provider: Literal["hash", "sentence-transformers", "openai"] = "hash"
    embeddings_model: str = "all-MiniLM-L6-v2"

    llm_api_key: SecretStr = SecretStr("")
    llm_base_url: str = "https://openai.generative.engine.capgemini.com/v1"
    llm_default_model: str = "openai.gpt-5.1"
    llm_temperature: float = Field(default=0.2, ge=0.0, le=1.5)
    llm_max_completion_tokens: int = Field(default=600, ge=1)
    llm_timeout_seconds: int = Field(default=55, ge=1)

    # Optional alias — some setups only export OPENAI_API_KEY.
    openai_api_key: SecretStr = SecretStr("")

    # --- rag ---------------------------------------------------------------
    upload_max_bytes: int = Field(default=26_214_400, ge=1)
    upload_allowed_extensions: CsvList
    rag_chunk_max_chars: int = Field(default=1400, ge=200)
    rag_chunk_min_chars: int = Field(default=40, ge=1)
    rag_chunk_overlap_chars: int = Field(default=180, ge=0)
    rag_top_k: int = Field(default=6, ge=1, le=50)

    # --- web retrieval -----------------------------------------------------
    web_retrieval_enabled: bool = False
    web_retrieval_allowlist: CsvList
    web_retrieval_timeout_seconds: int = Field(default=8, ge=1, le=60)
    web_retrieval_max_bytes: int = Field(default=2_097_152, ge=1)

    @field_validator(
        "cors_allowed_origins",
        "trusted_hosts",
        "upload_allowed_extensions",
        "web_retrieval_allowlist",
        mode="before",
    )
    @classmethod
    def _parse_csv(cls, value: object) -> list[str]:
        return _split_csv(value)

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            raise ValueError(f"Unsupported log level: {value}")
        return level

    @model_validator(mode="after")
    def _enforce_production_hardening(self) -> Settings:
        # Prefer LLM_API_KEY; fall back to OPENAI_API_KEY. Strip accidental whitespace/quotes.
        primary = self.llm_api_key.get_secret_value().strip().strip('"').strip("'")
        fallback = self.openai_api_key.get_secret_value().strip().strip('"').strip("'")
        resolved = primary or fallback
        object.__setattr__(self, "llm_api_key", SecretStr(resolved))

        # Local convenience: accept both localhost and 127.0.0.1 frontends.
        if self.environment is not Environment.PRODUCTION:
            origins = list(self.cors_allowed_origins)
            for origin in (
                "http://localhost:3000",
                "http://127.0.0.1:3000",
            ):
                if origin not in origins:
                    origins.append(origin)
            object.__setattr__(self, "cors_allowed_origins", origins)

        secret = self.jwt_secret_key.get_secret_value()

        if self.environment is Environment.PRODUCTION:
            problems: list[str] = []
            if self.auth_bypass:
                problems.append("AUTH_BYPASS must be false")
            if len(secret) < 32:
                problems.append("JWT_SECRET_KEY must be at least 32 characters")
            if not self.cookie_secure:
                problems.append("COOKIE_SECURE must be true")
            if not self.cors_allowed_origins:
                problems.append("CORS_ALLOWED_ORIGINS must list at least one origin")
            if "*" in self.cors_allowed_origins:
                problems.append("CORS_ALLOWED_ORIGINS must not contain '*'")
            if self.cookie_samesite == "none" and not self.cookie_secure:
                problems.append("COOKIE_SAMESITE=none requires COOKIE_SECURE=true")
            if problems:
                raise ValueError("Refusing to start in production: " + "; ".join(problems))
        elif len(secret) < 32:
            # Development convenience only. A restart invalidates existing tokens,
            # which is the correct behaviour for an unconfigured environment.
            object.__setattr__(self, "jwt_secret_key", SecretStr(secrets.token_urlsafe(64)))

        if self.db_pool_max_size < self.db_pool_min_size:
            raise ValueError("DB_POOL_MAX_SIZE must be >= DB_POOL_MIN_SIZE")

        return self

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @property
    def semantic_packs_dir(self) -> Path:
        return APP_ROOT / "semantic" / "packs"

    def analytics_database_url(self, industry: Industry) -> str:
        return {
            Industry.AUTOMOTIVE: self.automotive_database_url,
            Industry.INSURANCE: self.insurance_database_url,
        }[industry]

    def analytics_migrate_database_url(self, industry: Industry) -> str:
        return {
            Industry.AUTOMOTIVE: self.automotive_migrate_database_url,
            Industry.INSURANCE: self.insurance_migrate_database_url,
        }[industry]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton.

    Cached so that importing modules never re-read the environment, and so tests can
    clear the cache deliberately with ``get_settings.cache_clear()``.
    """
    return Settings()
