BEGIN TRANSACTION READ ONLY;

SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'procurement'
  AND table_name IN (
      'award',
      'award_transaction'
  )
ORDER BY
    table_name,
    ordinal_position;

COMMIT;
