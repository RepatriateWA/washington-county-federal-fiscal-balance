\set ON_ERROR_STOP on
\pset pager off
\echo '=============================================================='
\echo 'ETL-201Q STAGE A - HISTORICAL TRANSACTION SCHEMA PROFILE'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '=============================================================='
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;
SET LOCAL statement_timeout = '300s';
\echo ''
\echo 'SECTION 1 - ASSISTANCE TABLE INVENTORY'
SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema = 'assistance'
ORDER BY table_name;
\echo ''
\echo 'SECTION 2 - TRANSACTION AND LINKAGE COLUMN INVENTORY'
SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'assistance'
  AND (
      table_name ILIKE '%transaction%'
      OR table_name ILIKE '%recipient%'
      OR table_name ILIKE '%place%'
      OR table_name ILIKE '%geograph%'
      OR table_name = 'award'
  )
ORDER BY table_name, ordinal_position;
\echo ''
\echo 'SECTION 3 - PRIMARY AND FOREIGN KEY CONSTRAINTS'
SELECT
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type,
    kcu.column_name,
    ccu.table_name AS referenced_table,
    ccu.column_name AS referenced_column
FROM information_schema.table_constraints AS tc
LEFT JOIN information_schema.key_column_usage AS kcu
  ON kcu.constraint_schema = tc.constraint_schema
 AND kcu.constraint_name = tc.constraint_name
 AND kcu.table_name = tc.table_name
LEFT JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_schema = tc.constraint_schema
 AND ccu.constraint_name = tc.constraint_name
WHERE tc.table_schema = 'assistance'
  AND tc.constraint_type IN (
      'PRIMARY KEY',
      'FOREIGN KEY'
  )
ORDER BY
    tc.table_name,
    tc.constraint_type,
    tc.constraint_name,
    kcu.ordinal_position;
\echo ''
\echo 'SECTION 4 - RAW HISTORICAL BATCH COUNTS'
SELECT
    load_batch_id,
    COUNT(*) AS raw_observations,
    COUNT(DISTINCT assistance_award_unique_key)
        AS distinct_award_keys,
    COUNT(*) FILTER (
        WHERE assistance_award_unique_key IS NULL
    ) AS null_award_keys
FROM assistance.raw_award_transaction
WHERE load_batch_id IN (20, 21)
GROUP BY load_batch_id
ORDER BY load_batch_id;
ROLLBACK;
\echo ''
\echo 'ETL-201Q STAGE A COMPLETE - READ ONLY'