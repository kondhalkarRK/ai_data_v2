"""Shared response envelopes."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiModel(BaseModel):
    """Base for every response model.

    ``populate_by_name`` with camelCase aliases lets the API speak the frontend's
    convention while the Python code keeps snake_case.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        alias_generator=lambda field: "".join(
            part if index == 0 else part.capitalize()
            for index, part in enumerate(field.split("_"))
        ),
    )


class ErrorBody(ApiModel):
    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable message safe to show a user.")
    request_id: str = Field(description="Correlates with the server log entry.")
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(ApiModel):
    error: ErrorBody


class PageMeta(ApiModel):
    total: int | None = Field(
        default=None,
        description="Total matching rows when a bounded count was computed, otherwise null.",
    )
    limit: int
    next_cursor: str | None = None
    has_more: bool = False


class Page(ApiModel, Generic[T]):
    items: list[T]
    meta: PageMeta
