-- Legacy small daily cloning is retired: it can duplicate IDs, distort market mix,
-- and make a sparse day appear complete. This script deliberately performs NO writes.
-- Use scripts/refresh_automotive_increment.py to inspect, stage and review an increment.
-- See docs/automotive-increment-2026.md for backup, approval and load instructions.
DO $$
BEGIN
    RAISE EXCEPTION 'Legacy daily cloning is disabled. Use the reviewed Automotive increment workflow.';
END $$;
