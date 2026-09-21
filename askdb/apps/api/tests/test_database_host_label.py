from app.core.config import database_host_label


def test_database_host_label_distinguishes_local_and_supabase() -> None:
    assert "local" in database_host_label(
        "postgresql+psycopg://askdb_app:x@localhost:5432/askdb_app"
    )
    assert "supabase" in database_host_label(
        "postgresql+psycopg://postgres:x@db.abc.supabase.co:5432/postgres?sslmode=require"
    )
    assert "password" not in database_host_label(
        "postgresql+psycopg://postgres:secret-pass@db.abc.supabase.co:5432/postgres"
    )
