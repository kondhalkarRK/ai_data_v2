-- Run this file while connected to the default "postgres" database.
-- Replace the password before execution. Do not commit a real password.

CREATE ROLE askdb_app
    LOGIN
    PASSWORD 'REPLACE_WITH_A_STRONG_LOCAL_PASSWORD'
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT;

CREATE DATABASE askdb_dev
    WITH ENCODING = 'UTF8'
         TEMPLATE = template0;

-- Next: connect pgAdmin Query Tool to askdb_dev and run
-- db/migrations/001_insurance_schema.sql.
