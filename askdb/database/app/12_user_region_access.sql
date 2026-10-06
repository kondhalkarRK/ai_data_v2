-- ---------------------------------------------------------------------------
-- Ask DB - Region row-level access (askdb_app database)
--
--     python scripts/migrate.py app upgrade head
--     psql -d askdb_app -f database/app/12_user_region_access.sql
--     psql -d askdb_app -f database/app/13_seed_region_users.sql
-- ---------------------------------------------------------------------------

BEGIN;

CREATE TABLE IF NOT EXISTS user_region_access (
    user_region_id UUID        NOT NULL,
    user_id        UUID        NOT NULL,
    region_id      VARCHAR(40) NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_user_region_access PRIMARY KEY (user_region_id),
    CONSTRAINT uq_user_region_access_user_region UNIQUE (user_id, region_id),
    CONSTRAINT fk_user_region_access_user_id_auth_users
        FOREIGN KEY (user_id) REFERENCES auth_users (user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_user_region_access_user_id ON user_region_access (user_id);

COMMIT;
