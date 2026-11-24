BEGIN;
SET TRANSACTION READ ONLY;

SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'assistance'
  AND table_name = 'assistance_listing'
ORDER BY ordinal_position;

SELECT
    con.conname AS constraint_name,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint AS con
WHERE con.conrelid =
    'assistance.assistance_listing'::regclass
ORDER BY con.conname;

ROLLBACK;
