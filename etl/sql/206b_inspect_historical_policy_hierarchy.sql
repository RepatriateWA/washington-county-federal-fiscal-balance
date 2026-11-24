\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo '======================================================'
\echo 'ETL-206B - HISTORICAL CLASSIFICATION POLICY INSPECTION'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '======================================================'

\echo '=== 1. ACTUAL SOURCE-SYSTEM IDENTIFIERS ==='

SELECT
    source_system,
    methodology_version,
    COUNT(*) AS classifications
FROM reference.federal_inflow_award_classification
GROUP BY 1, 2
ORDER BY 1, 2;

\echo '=== 2. ETL-205 PERSISTENCE ==='

SELECT
    source_system,
    source_program_code,
    methodology_version,
    accounting_disposition,
    COUNT(*) AS awards,
    MIN(valid_from_fiscal_year) AS first_year,
    MAX(valid_through_fiscal_year) AS last_year
FROM reference.federal_inflow_award_classification
WHERE methodology_version = 'ANALYSIS-205-v1'
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2, 3, 4;

\echo '=== 3. POLICY TABLE COLUMN DEFINITIONS ==='

SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'reference'
  AND table_name IN (
      'federal_inflow_program_classification',
      'federal_inflow_program_policy_mapping',
      'federal_inflow_source_policy'
  )
ORDER BY table_name, ordinal_position;

\echo '=== 4. HCV POLICY RECORDS ==='

SELECT to_jsonb(p) AS policy_record
FROM reference.federal_inflow_program_classification p
WHERE to_jsonb(p)::text ILIKE '%14.871%';

SELECT to_jsonb(m) AS mapping_record
FROM reference.federal_inflow_program_policy_mapping m
WHERE to_jsonb(m)::text ILIKE '%14.871%';

SELECT to_jsonb(s) AS source_policy_record
FROM reference.federal_inflow_source_policy s
WHERE to_jsonb(s)::text ILIKE '%14.871%'
   OR to_jsonb(s)::text ILIKE '%housing choice voucher%';

\echo '=== 5. HCV AWARD CLASSIFICATIONS ==='

SELECT
    source_system,
    source_program_code,
    methodology_version,
    accounting_disposition,
    COUNT(*) AS awards,
    MIN(valid_from_fiscal_year) AS first_year,
    MAX(valid_through_fiscal_year) AS last_year
FROM reference.federal_inflow_award_classification
WHERE source_program_code = '14.871'
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2, 3, 4;

COMMIT;