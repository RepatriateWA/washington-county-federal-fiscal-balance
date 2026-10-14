\pset pager off
\set ON_ERROR_STOP on

BEGIN TRANSACTION READ ONLY;

\echo '========================================================'
\echo 'ETL-208B - HCV LEDGER RESOLUTION INSPECTION'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '========================================================'

\echo '=== 1. LEDGER VIEW COLUMNS ==='

SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'analysis'
  AND table_name IN (
      'v_certified_assistance_ledger',
      'v_assistance_transaction_observation_ledger'
  )
ORDER BY table_name, ordinal_position;

\echo '=== 2. CERTIFIED LEDGER VIEW DEFINITION ==='

SELECT pg_get_viewdef(
    'analysis.v_certified_assistance_ledger'::regclass,
    true
) AS view_definition;

\echo '=== 3. OBSERVATION LEDGER VIEW DEFINITION ==='

SELECT pg_get_viewdef(
    'analysis.v_assistance_transaction_observation_ledger'::regclass,
    true
) AS view_definition;

\echo '=== 4. ACCOUNTING DISPOSITION COLUMN INVENTORY ==='

SELECT
    table_schema,
    table_name,
    column_name
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
  AND (
       column_name ILIKE '%disposition%'
    OR column_name ILIKE '%ledger_treatment%'
    OR column_name ILIKE '%accounting_status%'
  )
ORDER BY table_schema, table_name, column_name;

COMMIT;

\echo 'ETL-208B READ-ONLY INSPECTION COMPLETE'