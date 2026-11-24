
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '===================================================='
\echo 'ETL-213C v0.1 - PROCUREMENT AGENCY LINKAGE INVENTORY'
\echo 'READ ONLY'
\echo '===================================================='

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '120s';

\echo '1. Agency, award and recipient columns'

SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'procurement'
  AND table_name IN (
      'agency',
      'award',
      'award_recipient_relationship',
      'recipient'
  )
ORDER BY table_name, ordinal_position;

\echo '2. Foreign-key relationships'

SELECT
    con.conrelid::regclass AS source_table,
    con.conname AS constraint_name,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint con
WHERE con.contype = 'f'
  AND con.conrelid IN (
      'procurement.award'::regclass,
      'procurement.award_transaction'::regclass,
      'procurement.agency'::regclass,
      'procurement.award_recipient_relationship'::regclass
  )
ORDER BY source_table, constraint_name;

\echo '3. Agency and award indexes'

SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'procurement'
  AND tablename IN (
      'agency',
      'award',
      'award_recipient_relationship'
  )
ORDER BY tablename, indexname;

ROLLBACK;

\echo 'ETL-213C v0.1 COMPLETE - NO DATABASE WRITES'
