-- Run against the Supabase `postgres` database as the postgres role (direct URI, port 5432).
-- One project holds app + automotive + insurance schemas (Free plan = 2 projects max,
-- so we do not create extra databases).
--
-- Replace passwords before running, or use scripts/seed_supabase_100k.ps1 which does it.

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
GRANT USAGE ON SCHEMA public TO askdb_app, askdb_owner;
GRANT CREATE ON SCHEMA public TO askdb_app, askdb_owner;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO askdb_app;
GRANT askdb_owner TO postgres;
GRANT askdb_app TO postgres;
