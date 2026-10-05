"""Authentication request and response models."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import EmailStr, Field, field_validator, model_validator

from app.auth.passwords import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from app.core.config import Industry
from app.models.enums import Role
from app.models.user import weekly_limits
from app.schemas.common import ApiModel


class LoginRequest(ApiModel):
    """``username`` also accepts the email address of accounts created before usernames."""

    username: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    remember_me: bool = True

    @field_validator("username")
    @classmethod
    def _username_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Username must not be blank.")
        return value.strip()

    @field_validator("password")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Password must not be blank.")
        return value


class UserProfile(ApiModel):
    id: uuid.UUID
    username: str
    email: str
    full_name: str
    role: Role
    default_industry: Industry
    is_active: bool
    must_change_password: bool
    weekly_token_limit: int | None = None
    weekly_call_limit: int | None = None
    last_login_at: datetime | None = None
    created_at: datetime

    @model_validator(mode="after")
    def _effective_limits(self) -> UserProfile:
        self.weekly_token_limit, self.weekly_call_limit = weekly_limits(
            self.role, self.weekly_token_limit, self.weekly_call_limit
        )
        return self


class SessionResponse(ApiModel):
    """Returned by login and refresh.

    No token is present in the body: they are delivered as HttpOnly cookies. Only the
    CSRF token is echoed, because the frontend must send it back in a header.
    """

    user: UserProfile
    csrf_token: str
    access_expires_at: datetime


class ChangePasswordRequest(ApiModel):
    current_password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class LogoutRequest(ApiModel):
    all_sessions: bool = False


class CreateUserRequest(ApiModel):
    username: str | None = Field(
        default=None, min_length=3, max_length=80, pattern=r"^[A-Za-z0-9._-]+$"
    )
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    role: Role = Role.USER
    default_industry: Industry = Industry.INSURANCE
    must_change_password: bool = True


class UpdateUserRoleRequest(ApiModel):
    role: Role


class UpdateUserActiveRequest(ApiModel):
    is_active: bool


class UpdatePreferencesRequest(ApiModel):
    default_industry: Industry
