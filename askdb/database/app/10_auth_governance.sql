-- ---------------------------------------------------------------------------
-- Ask DB - PoC authentication and AI governance schema (askdb_app database)
--
-- Tables: auth_users, login_audit, llm_usage, admin_audit, app_settings.
--
-- The supported path is the Alembic migration, which also upgrades an existing
-- database (renames "users" to "auth_users", maps analyst/viewer to user, ...):
--
--     python scripts/migrate.py app upgrade head
--
-- This script is the standalone equivalent for DBAs and for a fresh database. Every
-- statement is idempotent, so running it after the migration changes nothing.
--
--     psql -d askdb_app -f database/app/10_auth_governance.sql
--     psql -d askdb_app -f database/app/11_seed_poc_users.sql
-- ---------------------------------------------------------------------------

BEGIN;

-- Users ----------------------------------------------------------------------
-- Two roles only: 'admin' (Admin Center) and 'user'. Both have weekly AI quotas:
-- users default to 60,000 tokens and 50 calls; NULL limits on an admin row mean the
-- admin default applied by the API (60,000 tokens and 100 calls).
CREATE TABLE IF NOT EXISTS auth_users (
    user_id              UUID         NOT NULL,
    username             VARCHAR(80)  NOT NULL,
    email                VARCHAR(320) NOT NULL,
    email_normalized     VARCHAR(320) NOT NULL,
    full_name            VARCHAR(200) NOT NULL,
    password_hash        VARCHAR(255) NOT NULL,           -- Argon2id, never plaintext
    password_changed_at  TIMESTAMPTZ,
    must_change_password BOOLEAN      NOT NULL DEFAULT false,
    role                 VARCHAR(20)  NOT NULL DEFAULT 'user',
    default_industry     VARCHAR(20)  NOT NULL DEFAULT 'insurance',
    active               BOOLEAN      NOT NULL DEFAULT true,
    weekly_token_limit   INTEGER               DEFAULT 60000,
    weekly_call_limit    INTEGER               DEFAULT 50,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_login           TIMESTAMPTZ,
    CONSTRAINT pk_auth_users PRIMARY KEY (user_id),
    CONSTRAINT uq_auth_users_username UNIQUE (username),
    CONSTRAINT uq_auth_users_email_normalized UNIQUE (email_normalized)
);

CREATE INDEX IF NOT EXISTS ix_auth_users_role_active ON auth_users (role, active);

-- Login audit ------------------------------------------------------------------
-- One row per sign-in attempt. A successful session row is closed on logout
-- (logout_time set, status LOGOUT).
CREATE TABLE IF NOT EXISTS login_audit (
    audit_id    UUID        NOT NULL,
    user_id     UUID,
    username    VARCHAR(320),
    login_time  TIMESTAMPTZ NOT NULL DEFAULT now(),
    logout_time TIMESTAMPTZ,
    status      VARCHAR(10) NOT NULL,
    CONSTRAINT pk_login_audit PRIMARY KEY (audit_id),
    CONSTRAINT ck_login_audit_status CHECK (status IN ('SUCCESS', 'FAILED', 'LOGOUT')),
    CONSTRAINT fk_login_audit_user_id_auth_users
        FOREIGN KEY (user_id) REFERENCES auth_users (user_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_login_audit_user_time ON login_audit (user_id, login_time);

-- LLM usage ----------------------------------------------------------------------
-- One row per AI Chat question. Weekly quotas sum these rows from Monday 00:00 UTC,
-- so the allowance resets every week without a scheduled job.
CREATE TABLE IF NOT EXISTS llm_usage (
    usage_id           UUID          NOT NULL,
    user_id            UUID,
    question           TEXT,
    model_name         VARCHAR(120)  NOT NULL,
    execution_mode     VARCHAR(10)   NOT NULL DEFAULT 'LLM',
    prompt_tokens      INTEGER       NOT NULL DEFAULT 0,
    completion_tokens  INTEGER       NOT NULL DEFAULT 0,
    total_tokens       INTEGER       NOT NULL DEFAULT 0,
    response_time_ms   INTEGER,
    industry           VARCHAR(20),
    query_history_id   UUID,
    estimated_cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
    purpose            VARCHAR(40)   NOT NULL DEFAULT 'chat',
    created_at         TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT pk_llm_usage PRIMARY KEY (usage_id),
    CONSTRAINT ck_llm_usage_execution_mode
        CHECK (execution_mode IN ('SCHEMA', 'LLM', 'HYBRID', 'CACHE')),
    CONSTRAINT fk_llm_usage_user_id_auth_users
        FOREIGN KEY (user_id) REFERENCES auth_users (user_id)
);

-- A database created by the older activity schema already has llm_usage with
-- columns id / model and a foreign key to the old users table, so CREATE TABLE
-- above is skipped. Bring that table up to the current shape.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = current_schema() AND table_name = 'llm_usage'
                 AND column_name = 'id') THEN
        ALTER TABLE llm_usage RENAME COLUMN id TO usage_id;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = current_schema() AND table_name = 'llm_usage'
                 AND column_name = 'model') THEN
        ALTER TABLE llm_usage RENAME COLUMN model TO model_name;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_llm_usage_user') THEN
        ALTER TABLE llm_usage DROP CONSTRAINT fk_llm_usage_user;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_llm_usage_user_id_auth_users') THEN
        ALTER TABLE llm_usage ADD CONSTRAINT fk_llm_usage_user_id_auth_users
            FOREIGN KEY (user_id) REFERENCES auth_users (user_id) NOT VALID;
    END IF;
END $$;

ALTER TABLE llm_usage ADD COLUMN IF NOT EXISTS question TEXT;
ALTER TABLE llm_usage ADD COLUMN IF NOT EXISTS execution_mode VARCHAR(10) NOT NULL DEFAULT 'LLM';
ALTER TABLE llm_usage ADD COLUMN IF NOT EXISTS response_time_ms INTEGER;
ALTER TABLE llm_usage ADD COLUMN IF NOT EXISTS query_history_id UUID;
ALTER TABLE llm_usage ALTER COLUMN purpose SET DEFAULT 'chat';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_llm_usage_execution_mode') THEN
        ALTER TABLE llm_usage ADD CONSTRAINT ck_llm_usage_execution_mode
            CHECK (execution_mode IN ('SCHEMA', 'LLM', 'HYBRID', 'CACHE'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_llm_usage_user_created ON llm_usage (user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_llm_usage_mode_created ON llm_usage (execution_mode, created_at);

-- Admin audit --------------------------------------------------------------------
-- Logins, logouts, LLM changes, DQ / catalog / semantic / graph refreshes.
CREATE TABLE IF NOT EXISTS admin_audit (
    audit_id       UUID        NOT NULL,
    user_id        UUID,
    action         VARCHAR(80) NOT NULL,
    action_details TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_admin_audit PRIMARY KEY (audit_id),
    CONSTRAINT fk_admin_audit_user_id_auth_users
        FOREIGN KEY (user_id) REFERENCES auth_users (user_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_admin_audit_created ON admin_audit (created_at);
CREATE INDEX IF NOT EXISTS ix_admin_audit_action_created ON admin_audit (action, created_at);

-- Governed settings -------------------------------------------------------------
-- key 'llm': {"provider", "model", "temperature", "max_tokens", "updated_by"}
CREATE TABLE IF NOT EXISTS app_settings (
    key        VARCHAR(80) NOT NULL,
    value      JSONB       NOT NULL,
    updated_by UUID,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_app_settings PRIMARY KEY (key),
    CONSTRAINT fk_app_settings_updated_by_auth_users
        FOREIGN KEY (updated_by) REFERENCES auth_users (user_id) ON DELETE SET NULL
);

COMMIT;
