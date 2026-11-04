"""Read-only connectivity and migration check. Never prints database credentials."""

import json

import psycopg

from app.core.config import Settings

settings = Settings()
report = {}
for name, url in (
    ("application", settings.app_database_url),
    ("automotive", settings.automotive_database_url),
):
    try:
        with psycopg.connect(
            url.replace("postgresql+psycopg://", "postgresql://"),
            connect_timeout=3,
            options="-c default_transaction_read_only=on",
        ) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            report[name] = {"connected": cursor.fetchone()[0] == 1}
            if name == "application":
                cursor.execute("SELECT to_regclass('analytics_workspaces') IS NOT NULL")
                report[name]["workspace_table_exists"] = cursor.fetchone()[0]
    except Exception as exc:
        report[name] = {"connected": False, "error_type": type(exc).__name__}
print(json.dumps(report))
