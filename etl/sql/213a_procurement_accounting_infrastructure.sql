
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '======================================================'
\echo 'ETL-213A v0.1 - PROCUREMENT ACCOUNTING INFRASTRUCTURE'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '======================================================'

BEGIN TRANSACTION READ ONLY;

SET LOCAL statement_timeout = '120s';

\echo ''
\echo '1. Procurement tables and views'

SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema = 'procurement'
ORDER BY table_name;

\echo ''
\echo '2. Candidate classification, policy, and ledger objects'

SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    CASE c.relkind
        WHEN 'r' THEN 'TABLE'
        WHEN 'p' THEN 'PARTITIONED TABLE'
        WHEN 'v' THEN 'VIEW'
        WHEN 'm' THEN 'MATERIALIZED VIEW'
        ELSE c.relkind::text
    END AS object_type
FROM pg_class c
JOIN pg_namespace n
  ON n.oid = c.relnamespace
WHERE n.nspname NOT IN (
    'pg_catalog',
    'information_schema'
)
AND n.nspname NOT LIKE 'pg_toast%'
AND (
       c.relname ILIKE '%procurement%'
    OR c.relname ILIKE '%overlap%'
    OR c.relname ILIKE '%classification%'
    OR c.relname ILIKE '%ledger%'
    OR c.relname ILIKE '%policy%'
    OR c.relname ILIKE '%fiscal_balance%'
)
AND c.relkind IN ('r','p','v','m')
ORDER BY n.nspname, c.relname;

\echo ''
\echo '3. Canonical procurement transaction columns'

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'procurement'
  AND table_name = 'award_transaction'
ORDER BY ordinal_position;

\echo ''
\echo '4. Geographic relationship columns'

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'procurement'
  AND table_name = 'place_of_performance'
ORDER BY ordinal_position;

\echo ''
\echo '5. Existing indexes on procurement transactions'

SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'procurement'
  AND tablename IN (
      'award_transaction',
      'place_of_performance'
  )
ORDER BY tablename, indexname;

ROLLBACK;

\echo ''
\echo 'ETL-213A v0.1 COMPLETE - NO DATABASE WRITES'
