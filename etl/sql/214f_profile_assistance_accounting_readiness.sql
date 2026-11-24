
\set ON_ERROR_STOP on
\pset pager off

\echo '=========================================================='
\echo 'ETL-214F - ASSISTANCE ACCOUNTING READINESS'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '=========================================================='

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. PROGRAM POLICY MAPPINGS BY YEAR AND DISPOSITION'

WITH years AS (
    SELECT generate_series(2018, 2025) AS fiscal_year
)
SELECT
    y.fiscal_year,
    m.resolved_accounting_disposition,
    COUNT(*) AS mapping_records,
    COUNT(DISTINCT m.source_program_code) AS distinct_programs
FROM years y
JOIN reference.federal_inflow_program_policy_mapping m
  ON y.fiscal_year BETWEEN
       m.valid_from_fiscal_year
       AND m.valid_through_fiscal_year
GROUP BY
    y.fiscal_year,
    m.resolved_accounting_disposition
ORDER BY
    y.fiscal_year,
    m.resolved_accounting_disposition;

\echo ''
\echo '2. AWARD-LEVEL CLASSIFICATIONS BY YEAR'

WITH years AS (
    SELECT generate_series(2018, 2025) AS fiscal_year
)
SELECT
    y.fiscal_year,
    a.accounting_disposition,
    COUNT(*) AS classification_records
FROM years y
JOIN reference.federal_inflow_award_classification a
  ON y.fiscal_year BETWEEN
       a.valid_from_fiscal_year
       AND a.valid_through_fiscal_year
GROUP BY y.fiscal_year, a.accounting_disposition
ORDER BY y.fiscal_year, a.accounting_disposition;

\echo ''
\echo '3. RAILROAD PROGRAM MAPPINGS'

SELECT
    m.source_system,
    m.source_program_code,
    m.resolved_accounting_disposition,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    m.methodology_version
FROM reference.federal_inflow_program_policy_mapping m
WHERE m.source_program_code LIKE '57.%'
ORDER BY
    m.source_program_code,
    m.valid_from_fiscal_year;

\echo ''
\echo '4. CERTIFIED ASSISTANCE SOURCE VOLUME'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transaction_rows,
    COUNT(DISTINCT assistance_transaction_unique_key)
        AS distinct_transactions,
    ROUND(
        SUM(federal_action_obligation)::numeric, 2
    ) AS net_obligations_dollars,
    COUNT(*) FILTER (
        WHERE reference_county_id IS NOT NULL
    ) AS county_linked_rows,
    COUNT(*) FILTER (
        WHERE is_covid IS TRUE
    ) AS covid_flagged_rows
FROM analysis.v_certified_assistance_ledger
WHERE action_date_fiscal_year BETWEEN 2018 AND 2025
GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;

ROLLBACK;

\echo 'ETL-214F COMPLETE - NO DATABASE WRITES'
