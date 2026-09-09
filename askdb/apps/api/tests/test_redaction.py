"""Log redaction tests (spec section 18 and 20)."""

from __future__ import annotations

from app.observability.redaction import REDACTED, redact, redact_text


def test_redacts_database_password_in_dsn() -> None:
    dsn = "postgresql+psycopg://askdb_app:sup3r-s3cret@db.internal:5432/askdb_app"

    result = redact_text(dsn)

    assert "sup3r-s3cret" not in result
    assert REDACTED in result
    # The non-secret parts stay readable so the log is still useful.
    assert "db.internal:5432/askdb_app" in result


def test_redacts_bearer_header_and_jwt() -> None:
    token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.abcdefghijklmnop"

    assert token not in redact_text(f"Authorization: Bearer {token}")


def test_redacts_provider_api_key() -> None:
    assert "sk-abcdef0123456789abcdef" not in redact_text(
        "calling provider with sk-abcdef0123456789abcdef"
    )


def test_redacts_sensitive_keys_in_mapping() -> None:
    payload = {
        "email": "user@example.com",
        "password": "hunter2-but-longer",
        "llm_api_key": "sk-live-key",
        "prompt": "You are a helpful assistant with confidential context",
        "nested": {"refresh_token": "abc123", "safe": "keep me"},
    }

    result = redact(payload)

    assert result["email"] == "user@example.com"
    assert result["password"] == REDACTED
    assert result["llm_api_key"] == REDACTED
    assert result["prompt"] == REDACTED
    assert result["nested"]["refresh_token"] == REDACTED
    assert result["nested"]["safe"] == "keep me"


def test_truncates_very_long_strings() -> None:
    result = redact_text("x" * 5000)

    assert result.endswith("...[truncated]")
    assert len(result) < 5000


def test_handles_deep_structures_without_recursing_forever() -> None:
    deep: dict[str, object] = {"level": 0}
    cursor = deep
    for level in range(1, 20):
        child: dict[str, object] = {"level": level}
        cursor["child"] = child
        cursor = child

    # Must terminate rather than raise RecursionError.
    assert redact(deep) is not None
