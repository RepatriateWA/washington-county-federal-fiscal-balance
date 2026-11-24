\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo '======================================================'
\echo 'ETL-221I - STATEWIDE ASSISTANCE ACCOUNTING INSPECTION'
\echo 'FY2018-FY2024 - READ ONLY'
\echo '======================================================'

\echo ''
\echo '1. EXISTING STATEWIDE ASSISTANCE VIEW COLUMNS'

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'analysis'
  AND table_name = 'v_statewide_assistance_by_year'
ORDER BY ordinal_position;

\echo ''
\echo '2. EXISTING STATEWIDE ASSISTANCE VIEW DEFINITION'

SELECT pg_get_viewdef(
    'analysis.v_statewide_assistance_by_year'::regclass,
    true
) AS view_definition;

\echo ''
\echo '3. EXISTING STATEWIDE ASSISTANCE RESULTS'

SELECT *
FROM analysis.v_statewide_assistance_by_year
ORDER BY 1;

\echo ''
\echo '4. PROGRAM POLICY MAPPING COLUMNS'

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'reference'
  AND table_name = 'federal_inflow_program_policy_mapping'
ORDER BY ordinal_position;

\echo ''
\echo '5. AWARD CLASSIFICATION COLUMNS'

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'reference'
  AND table_name = 'federal_inflow_award_classification'
ORDER BY ordinal_position;

\echo ''
\echo '6. PROGRAM CLASSIFICATION COLUMNS'

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'reference'
  AND table_name = 'federal_inflow_program_classification'
ORDER BY ordinal_position;

\echo ''
\echo '7. HISTORICAL ASSISTANCE GEOGRAPHY VIEW COLUMNS'

SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'analysis'
  AND table_name IN (
      'v_assistance_geographic_attribution',
      'v_assistance_observation_geographic_attribution'
  )
ORDER BY table_name, ordinal_position;

ROLLBACK;