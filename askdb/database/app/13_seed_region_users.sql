-- ---------------------------------------------------------------------------
-- Ask DB - Region-scoped PoC users (askdb_app database)
--
--     admin       / admin123   all regions
--     user_north  / north123   North zone only
--     user_south  / south123   South zone only
--     user_west   / west123    West zone only
--     user_east   / east123    East zone only
--
-- Requires: 10_auth_governance.sql and 12_user_region_access.sql
-- (or `python scripts/migrate.py app upgrade head`).
-- Safe to re-run: existing usernames are left untouched.
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
        'a0000000-0000-4000-8000-000000000011', 'user_north',
        'user_north@askdb.local', 'user_north@askdb.local', 'North Region Analyst',
        '$argon2id$v=19$m=65536,t=3,p=4$Bj5xnN5HpgT+WAgItbEYag$bYMRZso7d67SBzvZnA/ePhAs4aAIA0VeEnyi+BpeX/E',
        false, 'user', 'automotive', true,
        60000, 50
    ),
    (
        'a0000000-0000-4000-8000-000000000012', 'user_south',
        'user_south@askdb.local', 'user_south@askdb.local', 'South Region Analyst',
        '$argon2id$v=19$m=65536,t=3,p=4$s2/5O5EOoJ8tTqwEgtlgPw$YTZm/fofn8yNaxxMlguZl4nNmQPJ681ccwnEHH9wl04',
        false, 'user', 'automotive', true,
        60000, 50
    ),
    (
        'a0000000-0000-4000-8000-000000000013', 'user_west',
        'user_west@askdb.local', 'user_west@askdb.local', 'West Region Analyst',
        '$argon2id$v=19$m=65536,t=3,p=4$uJuzPwa1TFja8+LaUnStxw$EtxCqZGHWhlrxsw9eYkQLxpKg0JMKObyT/l39n8bvZE',
        false, 'user', 'automotive', true,
        60000, 50
    ),
    (
        'a0000000-0000-4000-8000-000000000014', 'user_east',
        'user_east@askdb.local', 'user_east@askdb.local', 'East Region Analyst',
        '$argon2id$v=19$m=65536,t=3,p=4$trJonpe8y/QuvisfpJxquw$IRe6kwISb3cwQsbZotUCh+cjy1QX0zturWtOhPjpTy0',
        false, 'user', 'automotive', true,
        60000, 50
    )
ON CONFLICT DO NOTHING;

INSERT INTO user_region_access (user_region_id, user_id, region_id)
VALUES
    ('b0000000-0000-4000-8000-000000000011', 'a0000000-0000-4000-8000-000000000011', 'North'),
    ('b0000000-0000-4000-8000-000000000012', 'a0000000-0000-4000-8000-000000000012', 'South'),
    ('b0000000-0000-4000-8000-000000000013', 'a0000000-0000-4000-8000-000000000013', 'West'),
    ('b0000000-0000-4000-8000-000000000014', 'a0000000-0000-4000-8000-000000000014', 'East')
ON CONFLICT DO NOTHING;

COMMIT;

-- Check:
--   SELECT u.username, u.role, a.region_id
--   FROM auth_users u
--   LEFT JOIN user_region_access a ON a.user_id = u.user_id
--   ORDER BY u.username;
