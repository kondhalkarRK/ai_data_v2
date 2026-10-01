-- ---------------------------------------------------------------------------
-- Ask DB - PoC seed users (askdb_app database)
--
--     admin / admin123   role admin, unlimited AI usage
--     user1 / user123    role user, 60,000 tokens and 50 AI calls per week
--
-- Passwords are stored as Argon2id hashes. These short demo passwords skip the
-- 12-character policy the app enforces for accounts it creates, so use them for the
-- PoC only and change or disable both accounts before any shared deployment.
--
-- Safe to re-run: existing usernames / emails are left untouched.
-- Requires: 10_auth_governance.sql or `python scripts/migrate.py app upgrade head`.
-- ---------------------------------------------------------------------------

BEGIN;

INSERT INTO auth_users (
    user_id, username, email, email_normalized, full_name, password_hash,
    must_change_password, role, default_industry, active,
    weekly_token_limit, weekly_call_limit
)
VALUES
    (
        'a0000000-0000-4000-8000-000000000001', 'admin',
        'admin@askdb.local', 'admin@askdb.local', 'PoC Administrator',
        '$argon2id$v=19$m=65536,t=3,p=4$hft/LUxwNt68dix1bQhBPA$O1HahK8Vr+OFdIzi/OkzspPzAwzYPCUfij+aVSwioC0',
        false, 'admin', 'automotive', true,
        NULL, NULL
    ),
    (
        'a0000000-0000-4000-8000-000000000002', 'user1',
        'user1@askdb.local', 'user1@askdb.local', 'PoC User',
        '$argon2id$v=19$m=65536,t=3,p=4$Z+E/w0uJgyHXp5r0WGnz+g$MjJ82NYTzebsiUp5m3bPFV88zbEskqexgfgHPHQC0VA',
        false, 'user', 'automotive', true,
        60000, 50
    )
ON CONFLICT DO NOTHING;

COMMIT;

-- Check:
--   SELECT username, role, active, weekly_token_limit, weekly_call_limit FROM auth_users;
