
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo ''
\echo '=========================================================================='
\echo 'ETL-211M5B - VA CLASSIFICATION PRECEDENCE DISCOVERY'
\echo '=========================================================================='
\echo 'Fiscal years: 2018-2019'
\echo 'Mode: READ ONLY - NO DATABASE WRITES'
\echo '=========================================================================='

BEGIN TRANSACTION READ ONLY;

-- SECTION 1 - CLASSIFICATION TABLE STRUCTURES

\echo ''
\echo '1. CLASSIFICATION TABLE STRUCTURES'

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'reference'
  AND table_name IN (
      'federal_inflow_award_classification',
      'federal_inflow_program_classification'
  )
ORDER BY table_name, ordinal_position;


-- SECTION 2 - CLASSIFICATION TABLE CONSTRAINTS

\echo ''
\echo '2. CLASSIFICATION TABLE CONSTRAINTS'

SELECT
    c.conrelid::regclass AS table_name,
    c.conname AS constraint_name,
    pg_get_constraintdef(c.oid) AS definition
FROM pg_catalog.pg_constraint c
WHERE c.conrelid IN (
    'reference.federal_inflow_award_classification'::regclass,
    'reference.federal_inflow_program_classification'::regclass
)
ORDER BY table_name, constraint_name;



-- ==========================================================================
-- SECTION 3 - EXISTING VA PROGRAM CLASSIFICATIONS
-- ==========================================================================

\echo ''
\echo '3. EXISTING VA PROGRAM CLASSIFICATIONS'

SELECT
    p.source_system,
    p.source_program_code,
    p.source_program_title,
    p.inflow_family,
    p.inflow_subfamily,
    p.overlap_risk,
    p.covid_relevance,
    p.extraordinary_relevance,
    p.classification_basis,
    p.methodology_version,
    p.valid_from_fiscal_year,
    p.valid_through_fiscal_year
FROM reference.federal_inflow_program_classification p
WHERE p.source_program_code IN (
    '64.011', '64.012', '64.013',
    '64.039', '64.040', '64.041',
    '64.042', '64.043', '64.044',
    '64.045', '64.046', '64.047',
    '64.048', '64.049', '64.050'
)
ORDER BY
    p.source_system,
    p.source_program_code,
    p.valid_from_fiscal_year,
    p.methodology_version;



-- SECTION 4 - VA AWARD CLASSIFICATION INVENTORY

\echo ''
\echo '4. VA AWARD CLASSIFICATION INVENTORY'

SELECT
    COUNT(*) AS total_award_classification_rows,
    COUNT(*) FILTER (
        WHERE accounting_disposition = 'INCLUDE_ADDITIVE'
    ) AS additive_rows,
    COUNT(*) FILTER (
        WHERE accounting_disposition = 'EXCLUDE_DUPLICATE'
    ) AS duplicate_exclusion_rows,
    COUNT(*) FILTER (
        WHERE accounting_disposition NOT IN (
            'INCLUDE_ADDITIVE',
            'EXCLUDE_DUPLICATE'
        )
    ) AS other_disposition_rows
FROM reference.federal_inflow_award_classification;


-- SECTION 5 - POLICY MAPPING HISTORICAL COVERAGE

\echo ''
\echo '5. POLICY MAPPING HISTORICAL COVERAGE'

WITH medical_codes(program_code) AS (
    VALUES
        ('64.011'), ('64.012'), ('64.013'),
        ('64.039'), ('64.040'), ('64.041'),
        ('64.042'), ('64.043'), ('64.044'),
        ('64.045'), ('64.046'), ('64.047'),
        ('64.048'), ('64.049'), ('64.050')
)
SELECT
    m.source_program_code,
    m.methodology_version,
    m.resolved_accounting_disposition,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    s.preferred_source,
    s.allocation_source,
    s.ledger_treatment
FROM reference.federal_inflow_program_policy_mapping m
JOIN medical_codes codes
  ON codes.program_code = m.source_program_code
JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
ORDER BY
    m.source_program_code,
    m.valid_from_fiscal_year,
    m.methodology_version;

ROLLBACK;

\echo ''
\echo '=========================================================================='
\echo 'ETL-211M5B COMPLETE - NO DATABASE WRITES'
\echo '=========================================================================='
