"""Password hashing and policy.

Argon2id with the argon2-cffi defaults for the current library version, which track the
OWASP guidance. Parameters are recorded inside the encoded hash, so raising the cost later
does not invalidate existing hashes: ``needs_rehash`` detects stale ones at login time.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type

# time_cost=3, memory_cost=64 MiB, parallelism=4 is a reasonable server-side balance:
# roughly 50-100 ms per hash on typical hardware, which is slow enough to matter for an
# attacker and fast enough not to dominate a login request.
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256

# A dummy hash of a value nobody knows. Verified against when the email is unknown so a
# failed login costs the same time whether or not the account exists.
_DUMMY_HASH = _hasher.hash("nql-insight-timing-equaliser")


@dataclass(frozen=True, slots=True)
class PasswordPolicyResult:
    ok: bool
    problems: tuple[str, ...] = ()


def normalize_password(password: str) -> str:
    """Normalise Unicode so visually identical passwords compare equal."""
    return unicodedata.normalize("NFKC", password)


def check_password_policy(password: str, *, email: str | None = None) -> PasswordPolicyResult:
    """Validate a candidate password.

    Length is the dominant factor, so the rules stay deliberately simple: a long password
    with mixed character classes, not obviously derived from the account address.
    """
    candidate = normalize_password(password)
    problems: list[str] = []

    if len(candidate) < MIN_PASSWORD_LENGTH:
        problems.append(f"must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(candidate) > MAX_PASSWORD_LENGTH:
        problems.append(f"must be at most {MAX_PASSWORD_LENGTH} characters")
    if not re.search(r"[a-z]", candidate):
        problems.append("must contain a lowercase letter")
    if not re.search(r"[A-Z]", candidate):
        problems.append("must contain an uppercase letter")
    if not re.search(r"\d", candidate):
        problems.append("must contain a digit")
    if not re.search(r"[^\w\s]", candidate):
        problems.append("must contain a symbol")
    if email:
        local_part = email.split("@", 1)[0].lower()
        if len(local_part) >= 3 and local_part in candidate.lower():
            problems.append("must not contain the account name")

    return PasswordPolicyResult(ok=not problems, problems=tuple(problems))


def hash_password(password: str) -> str:
    return _hasher.hash(normalize_password(password))


def verify_password(password: str, encoded_hash: str | None) -> bool:
    """Verify a password, in constant-ish time whether or not a hash exists.

    Passing ``None`` still performs a full Argon2 verification against a dummy hash so
    the response time does not reveal that the account is unknown.
    """
    target = encoded_hash or _DUMMY_HASH
    try:
        _hasher.verify(target, normalize_password(password))
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return encoded_hash is not None


def needs_rehash(encoded_hash: str) -> bool:
    """True when the stored hash uses weaker parameters than the current policy."""
    try:
        return _hasher.check_needs_rehash(encoded_hash)
    except InvalidHashError:
        return True
