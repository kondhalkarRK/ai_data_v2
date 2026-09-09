-- ---------------------------------------------------------------------------
-- NQL Insight - cluster bootstrap
--
-- Creates the three databases and the two roles the application uses.
-- Runs once, on first start of an empty PostgreSQL data directory.
--
-- Passwords come from the environment when this is run by hand; the literals
-- below are development defaults only and must be changed for any deployed
-- environment.
-- ---------------------------------------------------------------------------

-- Application role: owns askdb_app, read/write.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'askdb_app') THEN
        CREATE ROLE askdb_app LOGIN PASSWORD 'askdb_app';
    END IF;
END
$$;

-- Analytics role: SELECT only on the two analytics databases.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'askdb_reader') THEN
        CREATE ROLE askdb_reader LOGIN PASSWORD 'askdb_reader';
    END IF;
END
$$;

-- Migration role: owns the analytics schemas so the reader never needs DDL rights.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'askdb_owner') THEN
        CREATE ROLE askdb_owner LOGIN PASSWORD 'askdb_owner';
    END IF;
END
$$;

SELECT 'CREATE DATABASE askdb_app OWNER askdb_app'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'askdb_app')\gexec

SELECT 'CREATE DATABASE askdb_automotive OWNER askdb_owner'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'askdb_automotive')\gexec

SELECT 'CREATE DATABASE askdb_insurance OWNER askdb_owner'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'askdb_insurance')\gexec

-- Deny the reader any ability to create objects, and let it connect.
\connect askdb_automotive
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE askdb_automotive TO askdb_reader;

\connect askdb_insurance
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE askdb_insurance TO askdb_reader;
