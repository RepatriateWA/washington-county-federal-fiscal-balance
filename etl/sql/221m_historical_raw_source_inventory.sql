\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo 'ETL-221M - HISTORICAL RAW SOURCE INVENTORY'

\echo ''
\echo '1. RAW ASSISTANCE TABLE - ALL COLUMNS'

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'assistance'
  AND table_name = 'raw_award_transaction'
ORDER BY ordinal_position;

\echo ''
\echo '2. PROCUREMENT LOAD BATCH - ALL COLUMNS'

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'procurement'
  AND table_name = 'load_batch'
ORDER BY ordinal_position;

\echo ''
\echo '3. HISTORICAL RAW ROW COUNTS'

SELECT
    load_batch_id,
    COUNT(*) AS raw_rows,
    MIN(source_row_number) AS first_source_row,
    MAX(source_row_number) AS last_source_row
FROM assistance.raw_award_transaction
WHERE load_batch_id IN (20, 21)
GROUP BY load_batch_id
ORDER BY load_batch_id;

ROLLBACK;