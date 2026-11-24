
\set ON_ERROR_STOP on
\pset pager off

\echo 'ETL-214B - EXISTING REPORTING COVERAGE'
\echo 'READ ONLY - NO DATABASE WRITES'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. EXISTING TRACKED EXPENDITURES BY YEAR AND PROGRAM'

SELECT
    report_year,
    agency_code,
    program_code,
    COUNT(*) AS reporting_rows,
    SUM(expenditure_dollars) AS expenditure_dollars
FROM reporting.v_washington_tracked_expenditures
WHERE report_year BETWEEN 2018 AND 2025
GROUP BY report_year, agency_code, program_code
ORDER BY report_year, agency_code, program_code;

\echo ''
\echo '2. EXISTING PARTIAL FISCAL BALANCE'

SELECT
    report_year,
    gross_collections_dollars,
    tracked_expenditures_dollars,
    partial_fiscal_balance_dollars,
    methodology_note
FROM reporting.v_washington_partial_fiscal_balance
WHERE report_year BETWEEN 2018 AND 2025
ORDER BY report_year;

ROLLBACK;

\echo 'ETL-214B COMPLETE - NO DATABASE WRITES'
