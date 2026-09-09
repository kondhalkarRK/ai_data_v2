"""JWT and refresh token tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.auth.tokens import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_refresh_token,
)
from app.core.config import Industry, Settings
from app.core.exceptions import TokenError
from app.models.enums import Role


def _claims_args() -> dict[str, object]:
    return {
        "user_id": uuid.uuid4(),
        "email": "analyst@example.com",
        "role": Role.ANALYST,
        "default_industry": Industry.INSURANCE,
        "session_id": uuid.uuid4(),
    }


def test_round_trip(settings: Settings) -> None:
    args = _claims_args()
    token, issued = create_access_token(settings, **args)  # type: ignore[arg-type]

    decoded = decode_access_token(settings, token)

    assert decoded.user_id == args["user_id"]
    assert decoded.role is Role.ANALYST
    assert decoded.default_industry is Industry.INSURANCE
    assert decoded.jti == issued.jti


def test_rejects_wrong_signing_key(settings: Settings) -> None:
    token, _ = create_access_token(settings, **_claims_args())  # type: ignore[arg-type]
    forged = jwt.encode(
        jwt.decode(token, options={"verify_signature": False}),
        "a-different-secret-entirely-that-is-long-enough-for-hs256",
        algorithm="HS256",
    )

    with pytest.raises(TokenError):
        decode_access_token(settings, forged)


def test_rejects_alg_none(settings: Settings) -> None:
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "x@example.com",
        "role": "admin",
        "industry": "insurance",
        "sid": str(uuid.uuid4()),
        "typ": "access",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        "jti": "forged",
    }
    unsigned = jwt.encode(payload, key="", algorithm="none")

    with pytest.raises(TokenError):
        decode_access_token(settings, unsigned)


def test_rejects_expired_token(settings: Settings) -> None:
    expired_at = datetime.now(UTC) - timedelta(minutes=5)
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "x@example.com",
        "role": "viewer",
        "industry": "automotive",
        "sid": str(uuid.uuid4()),
        "typ": "access",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int((expired_at - timedelta(minutes=15)).timestamp()),
        "exp": int(expired_at.timestamp()),
        "jti": "expired",
    }
    token = jwt.encode(
        payload, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm
    )

    with pytest.raises(TokenError) as excinfo:
        decode_access_token(settings, token)
    assert excinfo.value.code == "token_expired"


def test_rejects_wrong_audience(settings: Settings) -> None:
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "x@example.com",
        "role": "viewer",
        "industry": "automotive",
        "sid": str(uuid.uuid4()),
        "typ": "access",
        "iss": settings.jwt_issuer,
        "aud": "some-other-service",
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        "jti": "wrong-aud",
    }
    token = jwt.encode(
        payload, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm
    )

    with pytest.raises(TokenError):
        decode_access_token(settings, token)


def test_refresh_tokens_are_unique_and_hashed(settings: Settings) -> None:
    first = create_refresh_token(settings)
    second = create_refresh_token(settings)

    assert first.plaintext != second.plaintext
    assert first.family_id != second.family_id
    assert first.token_hash == hash_refresh_token(first.plaintext)
    assert len(first.token_hash) == 64
    # The stored form must not contain the secret.
    assert first.plaintext not in first.token_hash


def test_refresh_token_keeps_family_on_rotation(settings: Settings) -> None:
    original = create_refresh_token(settings)
    rotated = create_refresh_token(settings, family_id=original.family_id)

    assert rotated.family_id == original.family_id
    assert rotated.plaintext != original.plaintext
