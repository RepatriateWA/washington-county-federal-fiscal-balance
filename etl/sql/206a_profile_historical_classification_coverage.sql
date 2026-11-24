\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo '========================================================'
\echo 'ETL-206A - HISTORICAL ASSISTANCE CLASSIFICATION COVERAGE'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '========================================================'

\echo '=== 1. EXISTING AWARD CLASSIFICATIONS BY PROGRAM ==='

SELECT
    source_program_code,
    methodology_version,
    accounting_disposition,
    COUNT(*) AS classified_awards,
    MIN(valid_from_fiscal_year) AS first_fiscal_year,
    MAX(valid_through_fiscal_year) AS last_fiscal_year
FROM reference.federal_inflow_award_classification
WHERE source_system = 'USASPENDING'
  AND source_program_code IN (
      '96.002', '93.778', '96.001', '64.109',
      '96.004', '10.551', '96.006', '20.205',
      '93.774', '14.871', '84.063', '57.001'
  )
GROUP BY
    source_program_code,
    methodology_version,
    accounting_disposition
ORDER BY
    source_program_code,
    methodology_version,
    accounting_disposition;

\echo '=== 2. CLASSIFICATION TABLE STRUCTURE ==='

SELECT
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'reference'
  AND table_name = 'federal_inflow_award_classification'
ORDER BY ordinal_position;

\echo '=== 3. AVAILABLE POLICY TABLES ==='

SELECT
    table_schema,
    table_name
FROM information_schema.tables
WHERE table_schema IN ('reference', 'analysis')
  AND (
       table_name ILIKE '%inflow%policy%'
    OR table_name ILIKE '%classification%'
    OR table_name ILIKE '%overlap%'
  )
ORDER BY table_schema, table_name;

COMMIT;