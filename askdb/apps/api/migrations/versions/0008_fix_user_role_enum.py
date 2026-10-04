"""Normalize stale auth role values and remove mismatched user_role enum metadata.

This resolves local databases that were created with a stale enum definition or legacy
values like ``ADMIN``/``USER`` or ``analyst``/``viewer`` while the app now expects
``admin`` / ``user`` values.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008_fix_user_role_enum"
down_revision: str | None = "0007_auth_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Normalize the role column to the supported lowercase values expected by the app.
    op.execute("UPDATE auth_users SET role = 'user' WHERE role IN ('analyst', 'viewer', 'USER')")
    op.execute("UPDATE auth_users SET role = 'admin' WHERE role = 'ADMIN'")
    op.execute("UPDATE auth_users SET role = lower(role) WHERE role IS NOT NULL")

    # Some local databases have a stale PostgreSQL enum type for user_role; convert it to
    # a plain text column so the app can read the value without raising a LookupError.
    op.execute(
        "ALTER TABLE auth_users ALTER COLUMN role TYPE VARCHAR(20) USING role::text"
    )
    op.execute("DROP TYPE IF EXISTS user_role")


def downgrade() -> None:
    # Recreate the enum type in the old shape and cast back to it.
    op.execute("CREATE TYPE user_role AS ENUM ('admin', 'user')")
    op.execute(
        "ALTER TABLE auth_users ALTER COLUMN role TYPE user_role USING role::user_role"
    )
