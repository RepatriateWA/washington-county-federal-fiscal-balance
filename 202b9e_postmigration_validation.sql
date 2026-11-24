BEGIN TRANSACTION READ ONLY;

SELECT
    table_schema,
    table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'procurement'
  AND table_name = 'award_transaction_observation'
ORDER BY ordinal_position;

SELECT
    conname,
    contype,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid =
    'procurement.award_transaction_observation'::regclass
ORDER BY conname;

SELECT COUNT(*) AS observation_links
FROM procurement.award_transaction_observation;

COMMIT;
