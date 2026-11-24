
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-216A - STATEWIDE ACCOUNTING BASELINE'
\echo 'FY2018-FY2024 / READ ONLY / NO LEDGER CHANGES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. AVAILABLE ACCOUNTING OBJECTS'

WITH expected(schema_name, object_name) AS (
    VALUES
    ('reporting', 'v_washington_revenue_summary'),
    ('reporting', 'v_washington_tracked_expenditures'),
    ('reporting', 'v_washington_chip_expenditures'),
    ('reporting', 'v_washington_medicaid_expenditures'),
    ('reporting', 'v_washington_ssa_summary'),
    ('analysis', 'v_wa_federal_wage_allocation'),
    ('cms', 'medicare_core_state_year'),
    ('va', 'v_washington_county_gdx_control_total')
)
SELECT
    e.schema_name,
    e.object_name,
    CASE
        WHEN to_regclass(
            format('%I.%I', e.schema_name, e.object_name)
        ) IS NULL
        THEN 'MISSING'
        ELSE 'PRESENT'
    END AS availability
FROM expected e
ORDER BY e.schema_name, e.object_name;

\echo ''
\echo '2. IRS REVENUE CONTROL'

SELECT
    fiscal_year,
    gross_collections_dollars
FROM reporting.v_washington_revenue_summary
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year;

\echo ''
\echo '3. CURRENT TRACKED EXPENDITURE STREAMS'

SELECT
    report_year,
    agency_code,
    program_code,
    program_name,
    expenditure_dollars,
    measure_note
FROM reporting.v_washington_tracked_expenditures
WHERE report_year BETWEEN 2018 AND 2024
ORDER BY report_year, agency_code, program_code;

\echo ''
\echo '4. CMS CHIP CONTROL'

SELECT
    fiscal_year,
    federal_expenditure_amount,
    amount_method,
    is_additive_to_fiscal_balance,
    measure_note
FROM reporting.v_washington_chip_expenditures
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year;

\echo ''
\echo '5. CMS MEDICAID CONTROL'

SELECT
    fiscal_year,
    federal_expenditure_amount,
    amount_method,
    is_additive_to_fiscal_balance
FROM reporting.v_washington_medicaid_expenditures
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year;

\echo ''
\echo '6. SSA BENEFIT CONTROL'

SELECT
    report_year,
    program_code,
    program_name,
    annualized_benefits_dollars
FROM reporting.v_washington_ssa_summary
WHERE report_year BETWEEN 2018 AND 2024
ORDER BY report_year, program_code;

\echo ''
\echo '7. FEDERAL COMPENSATION ALLOCATION'

SELECT
    fiscal_year,
    allocated_wa_civilian_wage_dollars,
    allocated_wa_military_wage_dollars,
    allocated_wa_total_federal_wage_dollars
FROM analysis.v_wa_federal_wage_allocation
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year;

\echo ''
\echo '8. MEDICARE PERIOD AND COMPLETENESS STATUS'

SELECT
    calendar_year,
    original_medicare_actual_ffs_dollars,
    partc_reconstructed_dollars,
    partd_reconstructed_dollars,
    core_medicare_sum_dollars,
    partc_year_completeness,
    partd_coverage_status,
    combined_period_status,
    timing_basis_status,
    ledger_status
FROM cms.medicare_core_state_year
WHERE calendar_year BETWEEN 2018 AND 2024
  AND state_id = 48
ORDER BY calendar_year;

\echo ''
\echo '9. VA COUNTY CONTROL TOTALS'

SELECT
    fiscal_year,
    COUNT(DISTINCT county_id) AS counties,
    SUM(va_gdx_expenditure_amount) AS wa_total
FROM va.v_washington_county_gdx_control_total
WHERE fiscal_year BETWEEN 2018 AND 2024
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '10. COVERAGE COUNTS'

SELECT
    'IRS_REVENUE' AS source,
    COUNT(DISTINCT fiscal_year) AS years
FROM reporting.v_washington_revenue_summary
WHERE fiscal_year BETWEEN 2018 AND 2024

UNION ALL

SELECT
    'TRACKED_EXPENDITURES',
    COUNT(DISTINCT report_year)
FROM reporting.v_washington_tracked_expenditures
WHERE report_year BETWEEN 2018 AND 2024

UNION ALL

SELECT
    'CHIP',
    COUNT(DISTINCT fiscal_year)
FROM reporting.v_washington_chip_expenditures
WHERE fiscal_year BETWEEN 2018 AND 2024

UNION ALL

SELECT
    'MEDICAID',
    COUNT(DISTINCT fiscal_year)
FROM reporting.v_washington_medicaid_expenditures
WHERE fiscal_year BETWEEN 2018 AND 2024

UNION ALL

SELECT
    'FEDERAL_WAGES',
    COUNT(DISTINCT fiscal_year)
FROM analysis.v_wa_federal_wage_allocation
WHERE fiscal_year BETWEEN 2018 AND 2024;

ROLLBACK;

\echo ''
\echo 'ETL-216A COMPLETE - READ ONLY'
