\pset pager off
\set ON_ERROR_STOP on

BEGIN TRANSACTION READ ONLY;

\echo '========================================================'
\echo 'ETL-207D - HISTORICAL HCV RAW SOURCE DISCOVERY'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '========================================================'

\echo '=== 1. RAW TRANSACTION TABLE STRUCTURE ==='

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'assistance'
  AND table_name = 'raw_award_transaction'
ORDER BY ordinal_position;

\echo '=== 2. HISTORICAL RAW BATCH COUNTS ==='

SELECT
    load_batch_id,
    COUNT(*) AS raw_rows
FROM assistance.raw_award_transaction
WHERE load_batch_id IN (20, 21)
GROUP BY load_batch_id
ORDER BY load_batch_id;

\echo '=== 3. RAW TABLE CONSTRAINTS ==='

SELECT
    conname AS constraint_name,
    contype AS constraint_type,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'assistance.raw_award_transaction'::regclass
ORDER BY conname;

\echo '=== 4. ASSISTANCE-SCHEMA TABLE INVENTORY ==='

SELECT
    table_name
FROM information_schema.tables
WHERE table_schema = 'assistance'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;

COMMIT;

\echo 'ETL-207D READ-ONLY DISCOVERY COMPLETE'