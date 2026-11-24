\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo '=== PROGRAM POLICIES VALID IN FY2025 ==='

SELECT
    source_program_code,
    resolved_accounting_disposition,
    mapping_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND 2025 >= COALESCE(valid_from_fiscal_year, -2147483648)
  AND 2025 <= COALESCE(valid_through_fiscal_year, 2147483647)
ORDER BY source_program_code;

\echo '=== PROGRAM POLICY END-YEAR DISTRIBUTION ==='

SELECT
    valid_through_fiscal_year,
    COUNT(*) AS policy_count,
    COUNT(DISTINCT source_program_code) AS distinct_programs
FROM reference.federal_inflow_program_policy_mapping
WHERE source_system = 'USASPENDING_ASSISTANCE'
GROUP BY valid_through_fiscal_year
ORDER BY valid_through_fiscal_year NULLS LAST;

\echo '=== AWARD POLICY END-YEAR DISTRIBUTION ==='

SELECT
    valid_through_fiscal_year,
    COUNT(*) AS policy_count,
    COUNT(DISTINCT source_program_code) AS distinct_programs,
    COUNT(DISTINCT source_award_identifier) AS distinct_awards
FROM reference.federal_inflow_award_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
GROUP BY valid_through_fiscal_year
ORDER BY valid_through_fiscal_year NULLS LAST;

ROLLBACK;
