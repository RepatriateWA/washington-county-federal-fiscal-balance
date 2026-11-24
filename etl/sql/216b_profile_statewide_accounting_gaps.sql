
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-216B - STATEWIDE ACCOUNTING GAP PROFILE'
\echo 'FY2018-FY2024 / READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. TRACKED EXPENDITURES BY YEAR AND SOURCE'

SELECT
    report_year,
    agency_code,
    COUNT(*) AS program_rows,
    SUM(expenditure_dollars) AS tracked_dollars
FROM reporting.v_washington_tracked_expenditures
WHERE report_year BETWEEN 2018 AND 2024
GROUP BY report_year, agency_code
ORDER BY report_year, agency_code;

\echo ''
\echo '2. VA GDX COMPARED WITH TRACKED EXPENDITURES'

WITH va AS (
    SELECT
        fiscal_year,
        COUNT(DISTINCT county_id) AS counties,
        SUM(va_gdx_expenditure_amount) AS va_dollars
    FROM va.v_washington_county_gdx_control_total
    WHERE fiscal_year BETWEEN 2018 AND 2024
    GROUP BY fiscal_year
),
tracked AS (
    SELECT
        report_year,
        SUM(expenditure_dollars) AS tracked_dollars
    FROM reporting.v_washington_tracked_expenditures
    WHERE report_year BETWEEN 2018 AND 2024
    GROUP BY report_year
)
SELECT
    va.fiscal_year,
    va.counties,
    va.va_dollars,
    tracked.tracked_dollars,
    ROUND(
        100 * va.va_dollars
        / NULLIF(tracked.tracked_dollars, 0),
        2
    ) AS va_as_percent_of_tracked
FROM va
JOIN tracked
  ON tracked.report_year = va.fiscal_year
ORDER BY va.fiscal_year;

\echo ''
\echo '3. FEDERAL WAGES COMPARED WITH TRACKED EXPENDITURES'

WITH tracked AS (
    SELECT
        report_year,
        SUM(expenditure_dollars) AS tracked_dollars
    FROM reporting.v_washington_tracked_expenditures
    WHERE report_year BETWEEN 2018 AND 2024
    GROUP BY report_year
)
SELECT
    w.fiscal_year,
    w.allocated_wa_civilian_wage_dollars,
    w.allocated_wa_military_wage_dollars,
    w.allocated_wa_total_federal_wage_dollars,
    t.tracked_dollars,
    ROUND(
        100 * w.allocated_wa_total_federal_wage_dollars
        / NULLIF(t.tracked_dollars, 0),
        2
    ) AS wages_as_percent_of_tracked
FROM analysis.v_wa_federal_wage_allocation w
JOIN tracked t
  ON t.report_year = w.fiscal_year
WHERE w.fiscal_year BETWEEN 2018 AND 2024
ORDER BY w.fiscal_year;

\echo ''
\echo '4. SOURCE COVERAGE AND MEASURE NOTES'

SELECT
    agency_code,
    program_code,
    COUNT(DISTINCT report_year) AS years,
    MIN(report_year) AS first_year,
    MAX(report_year) AS last_year,
    COUNT(DISTINCT measure_note) AS distinct_measure_notes
FROM reporting.v_washington_tracked_expenditures
WHERE report_year BETWEEN 2018 AND 2024
GROUP BY agency_code, program_code
ORDER BY agency_code, program_code;

ROLLBACK;

\echo ''
\echo 'ETL-216B COMPLETE - READ ONLY'
