-- Optional, targeted display-name update for existing seeded demo accounts.
-- Run in the APPLICATION database only after reviewing matching accounts.
-- Does not change passwords, usernames, roles, industry or regional grants.
-- No automatic startup execution. Custom names are preserved.
BEGIN;
UPDATE auth_users SET full_name = 'Arpit'
WHERE email_normalized = 'admin@askdb.local' AND role = 'admin';

UPDATE auth_users SET full_name = 'Rahul'
WHERE email_normalized = 'user1@askdb.local' AND role = 'user'
  AND full_name = 'PoC User';
UPDATE auth_users SET full_name = 'Aarav'
WHERE email_normalized = 'user_north@askdb.local' AND role = 'user'
  AND full_name = 'North Region Analyst';
UPDATE auth_users SET full_name = 'Priya'
WHERE email_normalized = 'user_south@askdb.local' AND role = 'user'
  AND full_name = 'South Region Analyst';
UPDATE auth_users SET full_name = 'Vikram'
WHERE email_normalized = 'user_west@askdb.local' AND role = 'user'
  AND full_name = 'West Region Analyst';
UPDATE auth_users SET full_name = 'Ananya'
WHERE email_normalized = 'user_east@askdb.local' AND role = 'user'
  AND full_name = 'East Region Analyst';
COMMIT;
