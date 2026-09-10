#!/usr/bin/env python
"""Create the initial administrator account.

The password is never taken from a command-line argument, because arguments are visible
in shell history and in the process list. It is read from a hidden prompt, or from the
``NQL_ADMIN_PASSWORD`` environment variable for unattended provisioning.

Usage
-----
    python scripts/create_admin.py --email admin@example.com --name "Ada Lovelace"
    python scripts/create_admin.py --email admin@example.com --name "Ada" --generate
"""

from __future__ import annotations

import argparse
import asyncio
import selectors
import getpass
import os
import secrets
import string
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.auth.passwords import check_password_policy  # noqa: E402
from app.auth.rate_limit import FixedWindowRateLimiter  # noqa: E402
from app.auth.service import AuthService  # noqa: E402
from app.core.config import Industry, get_settings  # noqa: E402
from app.core.exceptions import ConflictError, ValidationError  # noqa: E402
from app.db.session import DatabaseRegistry  # noqa: E402
from app.models.enums import Role  # noqa: E402

PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{}"


def generate_password(length: int = 24) -> str:
    """Generate a password that satisfies the policy on the first try."""
    while True:
        candidate = "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))
        if check_password_policy(candidate).ok:
            return candidate


def read_password(*, generate: bool) -> tuple[str, bool]:
    """Return ``(password, was_generated)``."""
    if generate:
        return generate_password(), True

    from_env = os.environ.get("NQL_ADMIN_PASSWORD")
    if from_env:
        return from_env, False

    if not sys.stdin.isatty():
        raise SystemExit(
            "No terminal available for a password prompt. "
            "Set NQL_ADMIN_PASSWORD or pass --generate."
        )

    first = getpass.getpass("Password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise SystemExit("The passwords do not match.")
    return first, False


async def create_admin(
    *, email: str, full_name: str, password: str, industry: Industry, role: Role
) -> None:
    settings = get_settings()
    registry = DatabaseRegistry(settings)
    await registry.start()
    try:
        async with registry.app_session() as session:
            service = AuthService(
                session=session,
                settings=settings,
                login_limiter=FixedWindowRateLimiter(limit=1000),
            )
            existing = await service.users.get_by_email(email)
            if existing is not None:
                raise SystemExit(f"An account already exists for {email}.")

            user = await service.create_user(
                actor=None,
                email=email,
                full_name=full_name,
                password=password,
                role=role,
                default_industry=industry,
                # The operator running this script chose the password, so there is no
                # shared secret to rotate on first login.
                must_change_password=False,
            )
            print(f"Created {user.role.value} account {user.email} ({user.id}).")
    finally:
        await registry.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an NQL Insight administrator.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True, dest="full_name")
    parser.add_argument(
        "--industry",
        default=Industry.INSURANCE.value,
        choices=[member.value for member in Industry],
    )
    parser.add_argument(
        "--role", default=Role.ADMIN.value, choices=[member.value for member in Role]
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Generate a strong password and print it once.",
    )
    args = parser.parse_args()

    password, generated = read_password(generate=args.generate)

    policy = check_password_policy(password, email=args.email)
    if not policy.ok:
        print("The password does not meet the policy:", file=sys.stderr)
        for problem in policy.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2

    # try:
    #     asyncio.run(
    #         create_admin(
    #             email=args.email,
    #             full_name=args.full_name,
    #             password=password,
    #             industry=Industry(args.industry),
    #             role=Role(args.role),
    #         )
    #     )

    try:
        asyncio.run(
            create_admin(
                email=args.email,
                full_name=args.full_name,
                password=password,
                industry=Industry(args.industry),
                role=Role(args.role),
            ),
            loop_factory=lambda: asyncio.SelectorEventLoop(
                selectors.SelectSelector()
        ),
    )



    except (ConflictError, ValidationError) as exc:
        print(f"Failed: {exc.message}", file=sys.stderr)
        return 1

    if generated:
        print("\nGenerated password (shown once, store it in your password manager):")
        print(f"  {password}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
