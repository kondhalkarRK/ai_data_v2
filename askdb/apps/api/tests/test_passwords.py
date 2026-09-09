"""Password hashing and policy tests."""

from __future__ import annotations

import pytest

from app.auth.passwords import (
    check_password_policy,
    hash_password,
    normalize_password,
    verify_password,
)


def test_hash_is_argon2id_and_salted() -> None:
    first = hash_password("Correct-Horse-Battery-9!")
    second = hash_password("Correct-Horse-Battery-9!")

    assert first.startswith("$argon2id$")
    # Distinct salts mean identical passwords never share a hash.
    assert first != second


def test_verify_accepts_correct_and_rejects_wrong() -> None:
    encoded = hash_password("Correct-Horse-Battery-9!")

    assert verify_password("Correct-Horse-Battery-9!", encoded) is True
    assert verify_password("correct-horse-battery-9!", encoded) is False


def test_verify_against_missing_hash_is_false_but_still_runs() -> None:
    # Guards the timing-equalisation path used when an email is unknown.
    assert verify_password("anything-at-all-123!", None) is False


def test_unicode_normalisation() -> None:
    # NFD and NFC forms of the same string must authenticate identically.
    composed = "Café-Password-2026!"
    decomposed = "Cafe\u0301-Password-2026!"

    assert normalize_password(composed) == normalize_password(decomposed)
    assert verify_password(decomposed, hash_password(composed)) is True


@pytest.mark.parametrize(
    ("password", "expected_problem"),
    [
        ("Short1!", "must be at least 12 characters"),
        ("alllowercase123!", "must contain an uppercase letter"),
        ("ALLUPPERCASE123!", "must contain a lowercase letter"),
        ("NoDigitsHereAtAll!", "must contain a digit"),
        ("NoSymbolsHere12345", "must contain a symbol"),
    ],
)
def test_policy_rejects(password: str, expected_problem: str) -> None:
    result = check_password_policy(password)

    assert result.ok is False
    assert expected_problem in result.problems


def test_policy_rejects_password_containing_account_name() -> None:
    result = check_password_policy("Alice-Secure-2026!", email="alice@example.com")

    assert result.ok is False
    assert "must not contain the account name" in result.problems


def test_policy_accepts_a_strong_password() -> None:
    assert check_password_policy("Vh7!kRq2$mTx9pLw", email="admin@example.com").ok is True
