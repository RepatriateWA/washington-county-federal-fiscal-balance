
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-211N5 - HISTORICAL AL 64.029 MIGRATION PREPARATION'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. POLICY TABLE COLUMN DEFINITIONS'

SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'reference'
  AND table_name IN (
      'federal_inflow_program_classification',
      'federal_inflow_source_policy',
      'federal_inflow_program_policy_mapping'
  )
ORDER BY table_name, ordinal_position;

\echo ''
\echo '2. POLICY TABLE CONSTRAINTS'

SELECT
    conrelid::regclass AS table_name,
    conname AS constraint_name,
    pg_get_constraintdef(oid) AS constraint_definition
FROM pg_constraint
WHERE conrelid IN (
    'reference.federal_inflow_program_classification'::regclass,
    'reference.federal_inflow_source_policy'::regclass,
    'reference.federal_inflow_program_policy_mapping'::regclass
)
ORDER BY table_name, constraint_name;

\echo ''
\echo '3. PRIOR HISTORICAL MEDICAL CARE POLICY EXAMPLE'

SELECT *
FROM reference.federal_inflow_program_classification
WHERE methodology_version = 'ANALYSIS-211M-v1'
ORDER BY source_program_code
LIMIT 1;

SELECT *
FROM reference.federal_inflow_source_policy
WHERE methodology_version = 'ANALYSIS-211M-v1'
LIMIT 1;

SELECT *
FROM reference.federal_inflow_program_policy_mapping
WHERE methodology_version = 'ANALYSIS-211M-v1'
ORDER BY source_program_code
LIMIT 1;

\echo ''
\echo '4. EXISTING AL 64.029 CLASSIFICATIONS'

SELECT *
FROM reference.federal_inflow_program_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '64.029'
ORDER BY methodology_version;

ROLLBACK;

\echo ''
\echo 'ETL-211N5 SCHEMA INSPECTION COMPLETE'
