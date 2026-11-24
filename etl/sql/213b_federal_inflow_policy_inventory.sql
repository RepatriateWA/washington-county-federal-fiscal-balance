
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '========================================================'
\echo 'ETL-213B v0.1 - FEDERAL INFLOW POLICY INVENTORY'
\echo 'READ ONLY - NO TEMP TABLES OR DATABASE WRITES'
\echo '========================================================'

BEGIN TRANSACTION READ ONLY;

SET LOCAL statement_timeout = '120s';

\echo ''
\echo '1. Policy and classification table columns'

SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'reference'
  AND table_name IN (
      'federal_inflow_source_policy',
      'federal_inflow_program_classification',
      'federal_inflow_program_policy_mapping',
      'federal_inflow_award_classification'
  )
ORDER BY table_name, ordinal_position;

\echo ''
\echo '2. Policy and classification constraints'

SELECT
    c.conrelid::regclass AS table_name,
    c.conname AS constraint_name,
    pg_get_constraintdef(c.oid) AS definition
FROM pg_constraint c
WHERE c.conrelid IN (
    'reference.federal_inflow_source_policy'::regclass,
    'reference.federal_inflow_program_classification'::regclass,
    'reference.federal_inflow_program_policy_mapping'::regclass,
    'reference.federal_inflow_award_classification'::regclass
)
ORDER BY table_name, constraint_name;

\echo ''
\echo '3. Approximate policy table sizes'

SELECT
    relname AS table_name,
    n_live_tup AS estimated_rows
FROM pg_stat_user_tables
WHERE schemaname = 'reference'
  AND relname IN (
      'federal_inflow_source_policy',
      'federal_inflow_program_classification',
      'federal_inflow_program_policy_mapping',
      'federal_inflow_award_classification'
  )
ORDER BY relname;

\echo ''
\echo '4. Policy records mentioning procurement or contracts'

SELECT
    'federal_inflow_source_policy' AS source_table,
    to_jsonb(p) AS record
FROM reference.federal_inflow_source_policy p
WHERE to_jsonb(p)::text ~* 'procurement|contract|VA|GDX'
LIMIT 30;

\echo ''
\echo '5. Existing procurement-related award classifications'

SELECT
    to_jsonb(a) AS record
FROM reference.federal_inflow_award_classification a
WHERE to_jsonb(a)::text ~* 'procurement|contract'
LIMIT 30;

\echo ''
\echo '6. Program policy mappings referencing procurement'

SELECT
    to_jsonb(m) AS record
FROM reference.federal_inflow_program_policy_mapping m
WHERE to_jsonb(m)::text ~* 'procurement|contract'
LIMIT 30;

ROLLBACK;

\echo ''
\echo 'ETL-213B v0.1 COMPLETE - NO DATABASE WRITES'
