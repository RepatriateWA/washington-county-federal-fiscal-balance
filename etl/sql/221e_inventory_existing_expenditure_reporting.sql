\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo '============================================================'
\echo 'ETL-221E - EXISTING FEDERAL EXPENDITURE REPORTING INVENTORY'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

\echo ''
\echo '1. REPORTING VIEW DEFINITIONS'

SELECT
    schemaname,
    viewname,
    definition
FROM pg_views
WHERE schemaname = 'reporting'
  AND viewname IN (
      'v_federal_expenditures_by_state_year',
      'v_federal_expenditures_by_county_year'
  )
ORDER BY viewname;

\echo ''
\echo '2. REPORTING VIEW COLUMN DEFINITIONS'

SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'reporting'
  AND table_name IN (
      'v_federal_expenditures_by_state_year',
      'v_federal_expenditures_by_county_year'
  )
ORDER BY table_name, ordinal_position;

\echo ''
\echo '3. EXISTING LEDGER VIEW DEFINITIONS'

SELECT
    schemaname,
    viewname,
    definition
FROM pg_views
WHERE schemaname = 'analysis'
  AND viewname IN (
      'v_certified_assistance_ledger',
      'v_assistance_transaction_observation_ledger'
  )
ORDER BY viewname;

\echo ''
\echo '4. DEPENDENCIES OF REPORTING EXPENDITURE VIEWS'

SELECT DISTINCT
    v.relname AS reporting_view,
    source_ns.nspname AS source_schema,
    source.relname AS source_object
FROM pg_rewrite rewrite_rule
JOIN pg_class v
  ON v.oid = rewrite_rule.ev_class
JOIN pg_namespace v_ns
  ON v_ns.oid = v.relnamespace
JOIN pg_depend dependency
  ON dependency.objid = rewrite_rule.oid
JOIN pg_class source
  ON source.oid = dependency.refobjid
JOIN pg_namespace source_ns
  ON source_ns.oid = source.relnamespace
WHERE v_ns.nspname = 'reporting'
  AND v.relname IN (
      'v_federal_expenditures_by_state_year',
      'v_federal_expenditures_by_county_year'
  )
  AND dependency.refclassid = 'pg_class'::regclass
  AND source.oid <> v.oid
ORDER BY
    reporting_view,
    source_schema,
    source_object;

\echo ''
\echo '5. OTHER REPORTING VIEW NAMES'

SELECT
    table_name
FROM information_schema.views
WHERE table_schema = 'reporting'
ORDER BY table_name;

ROLLBACK;