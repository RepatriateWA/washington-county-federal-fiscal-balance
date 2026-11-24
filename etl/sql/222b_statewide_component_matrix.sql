\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-222B - STATEWIDE COMPONENT MATRIX'
\echo 'FY2018-FY2024 - READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. SEVEN-YEAR STATEWIDE COMPONENT MATRIX'

WITH
revenue AS (
    SELECT
        fiscal_year,
        gross_collections_dollars
    FROM reporting.v_washington_revenue_summary
    WHERE fiscal_year BETWEEN 2018 AND 2024
),
baseline AS (
    SELECT
        report_year AS fiscal_year,
        gross_collections_dollars,
        tracked_expenditures_dollars,
        partial_fiscal_balance_dollars,
        methodology_note
    FROM reporting.v_washington_partial_fiscal_balance
    WHERE report_year BETWEEN 2018 AND 2024
),
va AS (
    SELECT
        fiscal_year,
        SUM(va_gdx_expenditure_amount) AS va_gdx_dollars,
        COUNT(*) AS county_rows
    FROM va.v_washington_county_gdx_control_total
    WHERE fiscal_year BETWEEN 2018 AND 2024
    GROUP BY fiscal_year
),
wages AS (
    SELECT
        fiscal_year,
        allocated_wa_civilian_wage_dollars,
        allocated_wa_military_wage_dollars,
        allocated_wa_total_federal_wage_dollars,
        combined_allocation_confidence
    FROM analysis.v_wa_federal_wage_allocation
    WHERE fiscal_year BETWEEN 2018 AND 2024
)
SELECT
    r.fiscal_year,
    r.gross_collections_dollars AS irs_revenue_dollars,
    b.tracked_expenditures_dollars,
    v.va_gdx_dollars,
    w.allocated_wa_civilian_wage_dollars,
    w.allocated_wa_military_wage_dollars,
    w.allocated_wa_total_federal_wage_dollars,
    b.partial_fiscal_balance_dollars,
    v.county_rows AS va_county_rows,
    w.combined_allocation_confidence
FROM revenue r
LEFT JOIN baseline b USING (fiscal_year)
LEFT JOIN va v USING (fiscal_year)
LEFT JOIN wages w USING (fiscal_year)
ORDER BY r.fiscal_year;

\echo ''
\echo '2. CURRENTLY TRACKED EXPENDITURES BY SOURCE'

SELECT
    report_year,
    agency_code,
    program_code,
    program_name,
    SUM(expenditure_dollars) AS expenditure_dollars,
    MIN(measure_note) AS example_measure_note
FROM reporting.v_washington_tracked_expenditures
WHERE report_year BETWEEN 2018 AND 2024
GROUP BY
    report_year,
    agency_code,
    program_code,
    program_name
ORDER BY
    report_year,
    agency_code,
    program_code;

\echo ''
\echo '3. REVENUE CONSISTENCY CHECK'

SELECT
    r.fiscal_year,
    r.gross_collections_dollars AS irs_revenue,
    b.gross_collections_dollars AS baseline_revenue,
    r.gross_collections_dollars
        - b.gross_collections_dollars AS difference
FROM reporting.v_washington_revenue_summary r
JOIN reporting.v_washington_partial_fiscal_balance b
  ON b.report_year = r.fiscal_year
WHERE r.fiscal_year BETWEEN 2018 AND 2024
ORDER BY r.fiscal_year;

ROLLBACK;

\echo 'ETL-222B COMPLETE - NO DATABASE WRITES'