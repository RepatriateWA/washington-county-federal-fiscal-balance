\pset pager off
\set ON_ERROR_STOP on

BEGIN TRANSACTION READ ONLY;

\echo '============================================================'
\echo 'ETL-207G - HISTORICAL HCV POLICY EVIDENCE'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

\echo '=== 1. EXISTING HCV POLICY RECORDS ==='

SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'reference'
  AND table_name IN (
      'federal_inflow_source_policy',
      'federal_inflow_program_classification',
      'federal_inflow_program_policy_mapping'
  )
ORDER BY table_name, ordinal_position;

\echo '=== 2. HCV POLICY RECORDS AS JSON ==='

SELECT
    'SOURCE_POLICY' AS record_type,
    to_jsonb(p) AS policy_record
FROM reference.federal_inflow_source_policy p
WHERE to_jsonb(p)::text ILIKE '%14.871%'
   OR to_jsonb(p)::text ILIKE '%HOUSING_CHOICE_VOUCHERS%'
   OR to_jsonb(p)::text ILIKE '%HUD_VMS%';

SELECT
    'PROGRAM_CLASSIFICATION' AS record_type,
    to_jsonb(p) AS policy_record
FROM reference.federal_inflow_program_classification p
WHERE to_jsonb(p)::text ILIKE '%14.871%'
   OR to_jsonb(p)::text ILIKE '%HOUSING_CHOICE_VOUCHERS%';

SELECT
    'PROGRAM_POLICY_MAPPING' AS record_type,
    to_jsonb(p) AS policy_record
FROM reference.federal_inflow_program_policy_mapping p
WHERE to_jsonb(p)::text ILIKE '%14.871%'
   OR to_jsonb(p)::text ILIKE '%HOUSING_CHOICE_VOUCHERS%';

\echo '=== 3. HUD / VMS EVIDENCE TABLE INVENTORY ==='

SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema NOT IN (
    'pg_catalog',
    'information_schema'
)
  AND (
       table_schema ILIKE '%hud%'
    OR table_name ILIKE '%voucher%'
    OR table_name ILIKE '%vms%'
    OR table_name ILIKE '%housing%'
  )
ORDER BY table_schema, table_name;

\echo '=== 4. HISTORICAL HCV POLICY-TEXT DISCOVERY ==='

SELECT
    table_schema,
    table_name,
    column_name
FROM information_schema.columns
WHERE table_schema = 'reference'
  AND (
       column_name ILIKE '%methodology%'
    OR column_name ILIKE '%overlap%'
    OR column_name ILIKE '%evidence%'
    OR column_name ILIKE '%source%'
  )
  AND table_name ILIKE '%federal_inflow%'
ORDER BY table_name, ordinal_position;

COMMIT;

\echo 'ETL-207G READ-ONLY INSPECTION COMPLETE'