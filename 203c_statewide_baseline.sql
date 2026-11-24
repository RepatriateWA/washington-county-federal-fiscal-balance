BEGIN TRANSACTION READ ONLY;

-- REPORT 1: EXISTING PARTIAL FISCAL BALANCE
SELECT
    report_year,
    ROUND(gross_collections_dollars::numeric, 2)
        AS irs_gross_collections,
    ROUND(tracked_expenditures_dollars, 2)
        AS tracked_expenditures,
    ROUND(partial_fiscal_balance_dollars, 2)
        AS partial_balance
FROM reporting.v_washington_partial_fiscal_balance
WHERE report_year BETWEEN 2018 AND 2024
ORDER BY report_year;

-- REPORT 2: EXPENDITURE COMPONENTS
SELECT
    report_year,
    agency_code,
    program_code,
    COUNT(*) AS component_rows,
    ROUND(SUM(expenditure_dollars), 2)
        AS expenditure_dollars,
    STRING_AGG(DISTINCT measure_note, ' | ')
        AS accounting_basis
FROM reporting.v_washington_tracked_expenditures
WHERE report_year BETWEEN 2018 AND 2024
GROUP BY
    report_year,
    agency_code,
    program_code
ORDER BY
    report_year,
    agency_code,
    program_code;

COMMIT;