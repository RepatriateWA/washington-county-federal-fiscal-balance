\set ON_ERROR_STOP on

BEGIN READ ONLY;

\echo '=== MEDICAID ANNUAL CONTROL ROWS ==='

SELECT
    fiscal_year,
    state_id,
    state_fips,
    federal_program_id,
    federal_expenditure_amount,
    federal_share_medicaid,
    federal_share_arra,
    federal_share_covid,
    total_computable,
    state_share,
    expenditure_time_basis,
    control_total_label,
    source_file,
    source_worksheet,
    source_row_number
FROM reporting.v_washington_medicaid_expenditures
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year, federal_program_id, source_row_number;

\echo '=== CHIP ANNUAL REPORTING CONTROLS ==='

SELECT
    fiscal_year,
    state_id,
    state_fips,
    federal_program_id,
    federal_expenditure_amount,
    total_computable,
    state_share,
    additive_control_total_count,
    included_worksheet_types,
    source_workbooks,
    measure_note
FROM reporting.v_washington_chip_expenditures
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year;

\echo '=== YEARLY ROW CARDINALITY ==='

SELECT
    'MEDICAID' AS family,
    fiscal_year,
    count(*) AS reporting_rows,
    sum(federal_expenditure_amount) AS federal_amount
FROM reporting.v_washington_medicaid_expenditures
WHERE fiscal_year BETWEEN 2018 AND 2024
GROUP BY fiscal_year

UNION ALL

SELECT
    'CHIP' AS family,
    fiscal_year,
    count(*) AS reporting_rows,
    sum(federal_expenditure_amount) AS federal_amount
FROM reporting.v_washington_chip_expenditures
WHERE fiscal_year BETWEEN 2018 AND 2024
GROUP BY fiscal_year

ORDER BY family, fiscal_year;

ROLLBACK;
