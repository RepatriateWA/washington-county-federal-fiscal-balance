BEGIN TRANSACTION READ ONLY;

SELECT
    con.conname AS constraint_name,
    pg_get_constraintdef(con.oid) AS constraint_definition
FROM pg_constraint con
WHERE con.conrelid =
    'procurement.award_transaction'::regclass
ORDER BY con.conname;

SELECT
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'procurement'
  AND table_name = 'award_transaction'
  AND column_name IN ('naics_code', 'psc_code')
ORDER BY column_name;

COMMIT;