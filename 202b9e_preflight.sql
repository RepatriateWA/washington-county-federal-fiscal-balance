BEGIN TRANSACTION READ ONLY;

SELECT
    table_schema,
    table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'procurement'
  AND table_name IN (
      'raw_award_transaction',
      'award_transaction',
      'award',
      'award_transaction_observation'
  )
ORDER BY table_name, ordinal_position;

SELECT
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type,
    kcu.column_name
FROM information_schema.table_constraints tc
LEFT JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
   AND tc.table_schema = kcu.table_schema
WHERE tc.table_schema = 'procurement'
  AND tc.table_name IN (
      'raw_award_transaction',
      'award_transaction',
      'award_transaction_observation'
  )
ORDER BY tc.table_name, tc.constraint_name, kcu.ordinal_position;

SELECT
    COUNT(*) AS raw_observations,
    COUNT(*) FILTER (
        WHERE raw_record ? 'contract_transaction_unique_key'
    ) AS official_transaction_keys_present,
    COUNT(*) FILTER (
        WHERE raw_record ? 'contract_award_unique_key'
    ) AS official_award_keys_present
FROM procurement.raw_award_transaction;

SELECT
    COUNT(*) AS canonical_transactions,
    COUNT(DISTINCT usaspending_transaction_id)
        AS distinct_transaction_keys
FROM procurement.award_transaction;

COMMIT;
