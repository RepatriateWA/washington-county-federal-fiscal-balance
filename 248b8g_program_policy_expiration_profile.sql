\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo '=== FY2024-ENDING PROGRAM POLICIES BY DISPOSITION ==='

SELECT
    resolved_accounting_disposition,
    COUNT(*) AS policy_count,
    COUNT(DISTINCT source_program_code) AS distinct_programs
FROM reference.federal_inflow_program_policy_mapping
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND valid_through_fiscal_year = 2024
GROUP BY resolved_accounting_disposition
ORDER BY policy_count DESC, resolved_accounting_disposition;

\echo '=== FY2024-ENDING PROGRAM POLICY INVENTORY ==='

SELECT
    source_program_code,
    resolved_accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND valid_through_fiscal_year = 2024
ORDER BY source_program_code, resolved_accounting_disposition;

ROLLBACK;
