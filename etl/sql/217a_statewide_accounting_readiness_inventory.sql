
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-217A - STATEWIDE ACCOUNTING READINESS INVENTORY'
\echo 'FY2018-FY2024 / READ ONLY / NO LEDGER PROMOTION'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. REQUIRED ACCOUNTING OBJECTS'

WITH expected(schema_name, object_name) AS (
    VALUES
    ('reporting','v_washington_revenue_summary'),
    ('reporting','v_washington_tracked_expenditures'),
    ('reporting','v_washington_chip_expenditures'),
    ('reporting','v_washington_medicaid_expenditures'),
    ('reporting','v_washington_ssa_summary'),
    ('cms','medicare_core_state_year'),
    ('analysis','v_wa_federal_wage_allocation'),
    ('va','v_washington_county_gdx_control_total')
)
SELECT
    schema_name,
    object_name,
    CASE WHEN to_regclass(
        format('%I.%I',schema_name,object_name)
    ) IS NULL THEN 'MISSING' ELSE 'PRESENT' END AS status
FROM expected
ORDER BY schema_name,object_name;

DO $gate$
DECLARE v_missing integer;
BEGIN
    WITH expected(schema_name,object_name) AS (
        VALUES
        ('reporting','v_washington_revenue_summary'),
        ('reporting','v_washington_tracked_expenditures'),
        ('reporting','v_washington_chip_expenditures'),
        ('reporting','v_washington_medicaid_expenditures'),
        ('reporting','v_washington_ssa_summary'),
        ('cms','medicare_core_state_year'),
        ('analysis','v_wa_federal_wage_allocation'),
        ('va','v_washington_county_gdx_control_total')
    )
    SELECT COUNT(*) INTO v_missing
    FROM expected
    WHERE to_regclass(
        format('%I.%I',schema_name,object_name)
    ) IS NULL;

    IF v_missing <> 0 THEN
        RAISE EXCEPTION
            'BLOCK: % required accounting objects missing',
            v_missing;
    END IF;

    RAISE NOTICE 'ACCOUNTING OBJECT INVENTORY PASS';
END
$gate$;

\echo ''
\echo '2. IRS FEDERAL REVENUE CONTROLS'

SELECT fiscal_year,gross_collections_dollars
FROM reporting.v_washington_revenue_summary
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year;

\echo ''
\echo '3. TRACKED EXPENDITURE MEASURES - NOT A FINAL LEDGER'

SELECT
    report_year,
    agency_code,
    program_code,
    program_name,
    expenditure_dollars,
    measure_note
FROM reporting.v_washington_tracked_expenditures
WHERE report_year BETWEEN 2018 AND 2024
ORDER BY report_year,agency_code,program_code;

\echo ''
\echo '4. CMS CHIP AND MEDICAID ACCOUNTING FLAGS'

SELECT
    'CHIP' AS source,
    fiscal_year,
    federal_expenditure_amount,
    amount_method,
    is_additive_to_fiscal_balance
FROM reporting.v_washington_chip_expenditures
WHERE fiscal_year BETWEEN 2018 AND 2024

UNION ALL

SELECT
    'MEDICAID',
    fiscal_year,
    federal_expenditure_amount,
    amount_method,
    is_additive_to_fiscal_balance
FROM reporting.v_washington_medicaid_expenditures
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year,source;

\echo ''
\echo '5. SSA ANNUALIZATION EVIDENCE'

SELECT
    report_year,
    program_code,
    program_name,
    beneficiary_count,
    annualized_benefits_dollars
FROM reporting.v_washington_ssa_summary
WHERE report_year BETWEEN 2018 AND 2024
ORDER BY report_year,program_code;

\echo ''
\echo '6. MEDICARE PERIOD AND COMPLETENESS FLAGS'

SELECT
    calendar_year,
    original_medicare_actual_ffs_dollars,
    partc_reconstructed_dollars,
    partd_reconstructed_dollars,
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
\echo '7. FEDERAL WAGE ALLOCATION CONTROLS'

SELECT
    fiscal_year,
    allocated_wa_civilian_wage_dollars,
    allocated_wa_military_wage_dollars,
    allocated_wa_total_federal_wage_dollars
FROM analysis.v_wa_federal_wage_allocation
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year;

\echo ''
\echo '8. VA GDX ANNUAL EXPENDITURE CONTROLS'

SELECT
    fiscal_year,
    COUNT(*) AS county_rows,
    COUNT(DISTINCT county_id) AS counties,
    SUM(va_gdx_expenditure_amount) AS expenditure_dollars
FROM va.v_washington_county_gdx_control_total
WHERE fiscal_year BETWEEN 2018 AND 2024
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '9. VA SOURCE-POLICY COVERAGE'

SELECT
    methodology_version,
    preferred_source,
    allocation_source,
    ledger_treatment,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE inflow_family = 'VETERANS_AFFAIRS'
  AND inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
ORDER BY valid_from_fiscal_year;

ROLLBACK;

\echo ''
\echo 'ETL-217A COMPLETE - READ ONLY'
