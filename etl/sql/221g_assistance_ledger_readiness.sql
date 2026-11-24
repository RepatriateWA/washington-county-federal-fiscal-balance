\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo 'ETL-221G - ASSISTANCE LEDGER READINESS'
\echo 'READ ONLY - FY2018 THROUGH FY2024'

\echo ''
\echo '1. CERTIFIED LEDGER ROWS AND OBLIGATIONS'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transaction_rows,
    SUM(federal_action_obligation) AS obligations_dollars
FROM analysis.v_certified_assistance_ledger
WHERE action_date_fiscal_year BETWEEN 2018 AND 2024
GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;

\echo ''
\echo '2. SOURCE POLICY ACCOUNTING DISPOSITIONS'

SELECT
    ledger_treatment,
    inflow_family,
    COUNT(*) AS policy_rows,
    MIN(valid_from_fiscal_year) AS first_policy_year,
    MAX(valid_through_fiscal_year) AS last_policy_year
FROM reference.federal_inflow_source_policy
WHERE valid_from_fiscal_year <= 2024
  AND valid_through_fiscal_year >= 2018
GROUP BY ledger_treatment, inflow_family
ORDER BY inflow_family, ledger_treatment;

\echo ''
\echo '3. PROGRAM MAPPING DISPOSITIONS'

SELECT
    resolved_accounting_disposition,
    COUNT(*) AS mapping_rows,
    MIN(valid_from_fiscal_year) AS first_policy_year,
    MAX(valid_through_fiscal_year) AS last_policy_year
FROM reference.federal_inflow_program_policy_mapping
WHERE valid_from_fiscal_year <= 2024
  AND valid_through_fiscal_year >= 2018
GROUP BY resolved_accounting_disposition
ORDER BY resolved_accounting_disposition;

\echo ''
\echo '4. LEDGER VIEW DEFINITION'

SELECT pg_get_viewdef(
    'analysis.v_certified_assistance_ledger'::regclass,
    true
) AS view_definition;

ROLLBACK;