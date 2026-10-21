\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo 'ETL-221U6A - SEQUENCE AND ROLLBACK DIAGNOSTIC'
\echo 'READ ONLY - NO DATABASE WRITES'

\echo ''
\echo '1. CURRENT TABLE PRIMARY KEY MAXIMA'

SELECT
    'SOURCE_POLICY' AS table_name,
    COUNT(*) AS row_count,
    MAX(federal_inflow_source_policy_id) AS maximum_id
FROM reference.federal_inflow_source_policy

UNION ALL

SELECT
    'PROGRAM_MAPPING',
    COUNT(*),
    MAX(federal_inflow_program_policy_mapping_id)
FROM reference.federal_inflow_program_policy_mapping;

\echo ''
\echo '2. SEQUENCE NAMES'

SELECT
    pg_get_serial_sequence(
        'reference.federal_inflow_source_policy',
        'federal_inflow_source_policy_id'
    ) AS source_policy_sequence,
    pg_get_serial_sequence(
        'reference.federal_inflow_program_policy_mapping',
        'federal_inflow_program_policy_mapping_id'
    ) AS program_mapping_sequence;

\echo ''
\echo '3. PROGRAM MAPPING SEQUENCE STATUS'

SELECT
    schemaname,
    sequencename,
    last_value,
    start_value,
    increment_by,
    max_value,
    cycle
FROM pg_sequences
WHERE schemaname = 'reference'
  AND sequencename LIKE
      'federal_inflow_program_policy_mapping%';

\echo ''
\echo '4. FAILED MIGRATION RESIDUALS'

SELECT
    'SOURCE_POLICY' AS record_type,
    COUNT(*) AS remaining_rows
FROM reference.federal_inflow_source_policy
WHERE methodology_version LIKE 'ANALYSIS-221U-HIST-v1%'

UNION ALL

SELECT
    'PROGRAM_MAPPING',
    COUNT(*)
FROM reference.federal_inflow_program_policy_mapping
WHERE methodology_version = 'ANALYSIS-221U-HIST-v1';

\echo ''
\echo '5. EXISTING PROGRAM MAPPING ID 131'

SELECT
    federal_inflow_program_policy_mapping_id,
    source_system,
    source_program_code,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping
WHERE federal_inflow_program_policy_mapping_id = 131;

ROLLBACK;