BEGIN TRANSACTION READ ONLY;

SELECT
    fiscal_year,
    allocated_wa_civilian_wage_dollars,
    allocated_wa_military_wage_dollars,
    allocated_wa_total_federal_wage_dollars,
    combined_allocation_confidence,
    civilian_opm_blank_salary_employment_pct,
    civilian_omb_budget_vintage,
    military_omb_budget_vintage,
    civilian_value_status,
    military_value_status
FROM analysis.v_wa_federal_wage_allocation
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year;

SELECT
    fiscal_year,
    accounting_measure,
    scope,
    value_status,
    total_wage_obligations_dollars
FROM omb.v_federal_wage_obligation_control
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year;

SELECT
    report_year,
    agency_code,
    program_code,
    program_name,
    COUNT(*) AS reporting_rows
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

ROLLBACK;