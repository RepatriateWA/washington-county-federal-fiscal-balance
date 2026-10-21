
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo 'ETL-223N1 - FIVE-PROGRAM POLICY PREFLIGHT'
\echo 'READ ONLY - NO DATABASE WRITES'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. SOURCE POLICY TABLE COLUMNS'

SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'reference'
  AND table_name = 'federal_inflow_source_policy'
ORDER BY ordinal_position;

\echo ''
\echo '2. PROGRAM MAPPING TABLE COLUMNS'

SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'reference'
  AND table_name = 'federal_inflow_program_policy_mapping'
ORDER BY ordinal_position;

\echo ''
\echo '3. ACCOUNTING CLASSIFICATION TABLE CANDIDATES'

SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema IN ('reference', 'analysis', 'assistance')
  AND (
      table_name ILIKE '%accounting%classification%'
      OR table_name ILIKE '%source_program%classification%'
  )
ORDER BY table_schema, table_name, ordinal_position;

\echo ''
\echo '4. EXISTING TARGET SOURCE POLICIES'

SELECT
    inflow_family,
    inflow_subfamily,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE (
    inflow_family = 'NUTRITION_ASSISTANCE'
    AND inflow_subfamily IN ('WIC','SNAP_STATE_ADMINISTRATION')
)
OR (
    inflow_family = 'AGRICULTURAL_ASSISTANCE'
    AND inflow_subfamily = 'CONSERVATION_STEWARDSHIP'
)
OR (
    inflow_family = 'PUBLIC_HEALTH_ASSISTANCE'
    AND inflow_subfamily = 'HEALTH_CENTER_ACA_GRANTS'
)
OR (
    inflow_family = 'FAMILY_SUPPORT_ASSISTANCE'
    AND inflow_subfamily = 'CHILD_SUPPORT_SERVICES'
);

\echo ''
\echo '5. TARGET PROGRAM MAPPINGS - ALL VERSIONS'

SELECT
    source_program_code,
    resolved_accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND BTRIM(source_program_code) IN (
      '10.557','10.561','10.924','93.527','93.563'
  )
ORDER BY source_program_code, methodology_version;

COMMIT;

\echo 'ETL-223N1 COMPLETE - NO DATABASE WRITES'
