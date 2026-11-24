
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-214D - STATEWIDE ACCOUNTING SOURCE CONTROLS'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. IRS GROSS COLLECTIONS'

SELECT
    fiscal_year,
    gross_collections_dollars
FROM reporting.v_washington_revenue_summary
WHERE fiscal_year BETWEEN 2018 AND 2025
ORDER BY fiscal_year;

\echo ''
\echo '2. SSA OASDI ANNUALIZED BENEFITS'

SELECT
    report_year,
    program_code,
    annualized_benefits_dollars
FROM reporting.v_washington_ssa_summary
WHERE report_year BETWEEN 2018 AND 2025
ORDER BY report_year, program_code;

\echo ''
\echo '3. MEDICARE CORE - SOURCE-NATIVE CALENDAR YEARS'

SELECT
    m.calendar_year,
    m.original_medicare_actual_ffs_dollars,
    m.partc_reconstructed_dollars,
    m.partd_reconstructed_dollars,
    m.core_medicare_sum_dollars,
    m.partc_months_processed,
    m.partc_year_completeness,
    m.partd_coverage_status,
    m.timing_basis_status,
    m.ledger_status
FROM cms.medicare_core_state_year m
JOIN reference.state_registry s
    ON s.state_id = m.state_id
WHERE s.state_abbreviation = 'WA'
  AND m.calendar_year BETWEEN 2018 AND 2025
ORDER BY m.calendar_year;

\echo ''
\echo '4. VA GDX ANNUAL STATEWIDE EXPENDITURE CONTROLS'

SELECT
    fiscal_year,
    COUNT(DISTINCT county_id) AS counties,
    ROUND(
        SUM(va_gdx_expenditure_amount)::numeric,
        2
    ) AS statewide_expenditures_dollars
FROM va.v_washington_county_gdx_control_total
WHERE fiscal_year BETWEEN 2018 AND 2025
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '5. FEDERAL WAGE ALLOCATIONS'

SELECT
    fiscal_year,
    allocated_wa_civilian_wage_dollars,
    allocated_wa_military_wage_dollars,
    allocated_wa_total_federal_wage_dollars,
    civilian_value_status,
    military_value_status,
    combined_allocation_confidence,
    certification_methodology_version
FROM analysis.v_wa_federal_wage_allocation
WHERE fiscal_year BETWEEN 2018 AND 2025
ORDER BY fiscal_year;

\echo ''
\echo '6. EXISTING PARTIAL REPORT - COMPARISON ONLY'

SELECT
    report_year,
    gross_collections_dollars,
    tracked_expenditures_dollars,
    partial_fiscal_balance_dollars
FROM reporting.v_washington_partial_fiscal_balance
WHERE report_year BETWEEN 2018 AND 2025
ORDER BY report_year;

ROLLBACK;

\echo 'ETL-214D COMPLETE - NO DATABASE WRITES'
