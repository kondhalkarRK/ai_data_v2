"""Create askdb_app / askdb_reader / askdb_owner when psql is not available (Supabase)."""

from __future__ import annotations

import os
import sys

import psycopg

SQL = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'askdb_app') THEN
        CREATE ROLE askdb_app LOGIN PASSWORD 'askdb_app_change_me';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'askdb_reader') THEN
        CREATE ROLE askdb_reader LOGIN PASSWORD 'askdb_reader_change_me';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'askdb_owner') THEN
        CREATE ROLE askdb_owner LOGIN PASSWORD 'askdb_owner_change_me';
    END IF;
END
$$;
GRANT CONNECT ON DATABASE postgres TO askdb_app, askdb_reader, askdb_owner;
GRANT CREATE ON DATABASE postgres TO askdb_owner, askdb_app;
GRANT USAGE, CREATE ON SCHEMA public TO askdb_app, askdb_owner;
"""


def main() -> None:
    url = (os.environ.get("SUPABASE_DIRECT_URI") or "").strip()
    if not url:
        raise SystemExit("SUPABASE_DIRECT_URI is not set")
    url = url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(url) as conn:
        conn.execute(SQL)
        conn.commit()
    print("Analytics roles ready (askdb_app, askdb_reader, askdb_owner).")


if __name__ == "__main__":
    sys.exit(main())
