"""JWT access tokens and opaque refresh tokens.

Access tokens are short-lived signed JWTs carrying the claims a request needs, so no
database round-trip is required to authorise a call. Refresh tokens are opaque random
strings — there is nothing useful to read in them and they are only ever stored hashed.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import jwt

from app.core.config import Industry, Settings
from app.core.exceptions import TokenError
from app.models.enums import Role

ACCESS_TOKEN_TYPE: Final = "access"  # noqa: S105 - a claim discriminator, not a secret
REFRESH_TOKEN_BYTES: Final = 48


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    email: str
    role: Role
    default_industry: Industry
    session_id: uuid.UUID
    issued_at: datetime
    expires_at: datetime
    jti: str


@dataclass(frozen=True, slots=True)
class IssuedRefreshToken:
    """A freshly minted refresh token.

    ``plaintext`` is returned to the client exactly once, in a cookie. Only ``token_hash``
    is persisted.
    """

    plaintext: str
    token_hash: str
    family_id: uuid.UUID
    expires_at: datetime


def _now() -> datetime:
    return datetime.now(UTC)


def create_access_token(
    settings: Settings,
    *,
    user_id: uuid.UUID,
    email: str,
    role: Role,
    default_industry: Industry,
    session_id: uuid.UUID,
) -> tuple[str, AccessTokenClaims]:
    issued_at = _now()
    expires_at = issued_at + timedelta(minutes=settings.jwt_access_ttl_minutes)
    jti = secrets.token_urlsafe(16)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "role": role.value,
        "industry": default_industry.value,
        "sid": str(session_id),
        "typ": ACCESS_TOKEN_TYPE,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(issued_at.timestamp()),
        "nbf": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": jti,
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    claims = AccessTokenClaims(
        user_id=user_id,
        email=email,
        role=role,
        default_industry=default_industry,
        session_id=session_id,
        issued_at=issued_at,
        expires_at=expires_at,
        jti=jti,
    )
    return token, claims


def decode_access_token(settings: Settings, token: str) -> AccessTokenClaims:
    """Verify and decode an access token, or raise ``TokenError``.

    Algorithm, issuer, audience and expiry are all verified. Pinning the algorithm list
    is what prevents the ``alg: none`` and HMAC/RSA confusion classes of attack.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["exp", "iat", "sub", "jti", "aud", "iss"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("The session has expired.", code="token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError() from exc

    if payload.get("typ") != ACCESS_TOKEN_TYPE:
        raise TokenError("Unexpected token type.")

    try:
        return AccessTokenClaims(
            user_id=uuid.UUID(str(payload["sub"])),
            email=str(payload["email"]),
            role=Role(str(payload["role"])),
            default_industry=Industry(str(payload["industry"])),
            session_id=uuid.UUID(str(payload["sid"])),
            issued_at=datetime.fromtimestamp(int(payload["iat"]), tz=UTC),
            expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
            jti=str(payload["jti"]),
        )
    except (KeyError, ValueError) as exc:
        raise TokenError("Malformed token claims.") from exc


def hash_refresh_token(plaintext: str) -> str:
    """Digest used as the stored representation of a refresh token.

    A plain SHA-256 is correct here, unlike for passwords: the input is 384 bits of
    cryptographic randomness, so there is nothing to brute force and no benefit to a slow
    hash.
    """
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def create_refresh_token(
    settings: Settings, *, family_id: uuid.UUID | None = None
) -> IssuedRefreshToken:
    plaintext = secrets.token_urlsafe(REFRESH_TOKEN_BYTES)
    return IssuedRefreshToken(
        plaintext=plaintext,
        token_hash=hash_refresh_token(plaintext),
        family_id=family_id or uuid.uuid4(),
        expires_at=_now() + timedelta(days=settings.jwt_refresh_ttl_days),
    )


def create_csrf_token() -> str:
    """Double-submit CSRF token.

    Readable by the browser (not HttpOnly) and echoed back in a header, which a
    cross-origin page cannot do.
    """
    return secrets.token_urlsafe(32)


def constant_time_equals(left: str, right: str) -> bool:
    return secrets.compare_digest(left, right)
