\pset pager off
\set ON_ERROR_STOP on

\echo ''
\echo '===================================================================================================='
\echo 'ETL-195 - DRAFT-1 2018-2019 ACCOUNTING RECONSTRUCTION v0.1'
\echo '===================================================================================================='
\echo 'READ ONLY - NO DATABASE WRITES'
\echo ''
\echo 'Purpose:'
\echo '  Extract explicit 2018-2019 Washington accounting controls needed to bridge'
\echo '  the historical partial fiscal-balance calculation to the DRAFT-1 methodology.'
\echo ''
\echo 'IMPORTANT:'
\echo '  Values are existing database observations.'
\echo '  Presence does not authorize ledger inclusion.'
\echo '  This script does not infer missing values.'
\echo '  This script does not resolve timing-basis differences.'
\echo '  This script does not resolve overlap.'
\echo '  This script does not change accounting policy.'
\echo ''

BEGIN;
SET TRANSACTION READ ONLY;


-- ================================================================================================
-- 1. LEGACY TRACKED-EXPENDITURE DECOMPOSITION
--
-- This should explain exactly what is already contained in the historical
-- $37.734B (2018) and $39.902B (2019) partial-balance expenditure totals.
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '1A. LEGACY TRACKED-EXPENDITURE DETAIL'
\echo '===================================================================================================='

SELECT
    report_year,
    agency_code,
    program_code,
    program_name,
    expenditure_dollars,
    measure_note
FROM reporting.v_washington_tracked_expenditures
WHERE report_year IN (2018, 2019)
ORDER BY
    report_year,
    agency_code,
    program_code;


\echo ''
\echo '===================================================================================================='
\echo '1B. LEGACY TRACKED-EXPENDITURE RECONCILIATION'
\echo '===================================================================================================='

WITH detail AS (
    SELECT
        report_year,
        expenditure_dollars
    FROM reporting.v_washington_tracked_expenditures
    WHERE report_year IN (2018, 2019)
),
detail_totals AS (
    SELECT
        report_year,
        SUM(expenditure_dollars) AS detail_sum_dollars,
        COUNT(*) AS component_rows
    FROM detail
    GROUP BY report_year
)
SELECT
    p.report_year,
    d.component_rows,
    d.detail_sum_dollars,
    p.tracked_expenditures_dollars AS published_partial_view_dollars,
    d.detail_sum_dollars - p.tracked_expenditures_dollars
        AS reconciliation_difference_dollars
FROM detail_totals AS d
JOIN reporting.v_washington_partial_fiscal_balance AS p
  ON p.report_year = d.report_year
ORDER BY p.report_year;


-- ================================================================================================
-- 2. SSA STATE SUMMARY
--
-- Query the established state reporting layer directly. This lets us compare the
-- state-level accounting representation with the county TOTAL observations seen in ETL-194.
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '2. SSA WASHINGTON STATE SUMMARY'
\echo '===================================================================================================='

SELECT
    report_year,
    program_code,
    program_name,
    beneficiary_count,
    annualized_benefits_thousands,
    annualized_benefits_dollars
FROM reporting.v_washington_ssa_summary
WHERE report_year IN (2018, 2019)
ORDER BY
    report_year,
    program_code;


-- ================================================================================================
-- 3. MEDICAID
--
-- Preserve all accounting metadata. Do not collapse federal-share components or
-- reinterpret the view's established federal_expenditure_amount.
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '3. WASHINGTON MEDICAID CONTROL'
\echo '===================================================================================================='

SELECT
    fiscal_year,
    state_name,
    federal_program_id,
    total_computable,
    federal_expenditure_amount,
    federal_share_medicaid,
    federal_share_arra,
    federal_share_covid,
    state_share,
    control_total_label,
    expenditure_time_basis,
    geographic_level,
    federal_agency_name,
    federal_program_name,
    amount_method,
    is_additive_to_fiscal_balance,
    source_file,
    source_worksheet,
    source_row_number
FROM reporting.v_washington_medicaid_expenditures
WHERE fiscal_year IN (2018, 2019)
ORDER BY fiscal_year;


-- ================================================================================================
-- 4. CHIP
--
-- ETL-194 showed empty current CHIP physical tables but an established reporting view.
-- Query the reporting layer directly. A zero-row result is evidence and must not be
-- interpreted as zero expenditure.
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '4. WASHINGTON CHIP CONTROL'
\echo '===================================================================================================='

SELECT
    fiscal_year,
    state_name,
    federal_program_id,
    total_computable,
    federal_expenditure_amount,
    state_share,
    additive_control_total_count,
    included_worksheet_types,
    geographic_level,
    federal_agency_name,
    federal_program_name,
    amount_method,
    is_additive_to_fiscal_balance,
    measure_note,
    source_workbooks
FROM reporting.v_washington_chip_expenditures
WHERE fiscal_year IN (2018, 2019)
ORDER BY fiscal_year;


-- ================================================================================================
-- 5. OPM / OMB CIVILIAN WAGE ALLOCATION
--
-- Retain suppression diagnostics and confidence designation.
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '5. OPM / OMB CIVILIAN WAGE ALLOCATION'
\echo '===================================================================================================='

SELECT
    fiscal_year,
    budget_vintage,
    value_status,
    accounting_measure,
    scope,
    omb_nonmilitary_wage_obligations_dollars,
    snapshot_month,
    workstat1_employment,
    workstat1_blank_salary_employment,
    workstat1_blank_salary_employment_pct,
    us_type_employment,
    us_type_known_salary_mass_dollars,
    us_type_blank_salary_employment,
    us_type_blank_salary_employment_pct,
    wa_employment,
    wa_known_salary_mass_dollars,
    wa_blank_salary_employment,
    wa_blank_salary_employment_pct,
    wa_known_salary_share,
    allocated_wa_civilian_wage_dollars,
    usps_excluded_employment,
    usps_excluded_known_salary_mass_dollars,
    allocation_confidence,
    methodology_version
FROM opm.v_omb_civilian_wage_allocation
WHERE fiscal_year IN (2018, 2019)
ORDER BY fiscal_year;


-- ================================================================================================
-- 6. COMBINED FEDERAL WAGE ALLOCATION
--
-- This is a reconciliation/control query. We retain civilian and military components
-- separately so that the combined value cannot conceal a component discrepancy.
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '6. COMBINED WASHINGTON FEDERAL WAGE ALLOCATION'
\echo '===================================================================================================='

SELECT
    fiscal_year,
    omb_civilian_wage_control_dollars,
    omb_military_wage_control_dollars,
    omb_total_federal_wage_control_dollars,
    civilian_wa_allocation_share,
    civilian_wa_allocation_share_percent,
    allocated_wa_civilian_wage_dollars,
    military_wa_allocation_share,
    military_wa_allocation_share_percent,
    allocated_wa_military_wage_dollars,
    allocated_wa_total_federal_wage_dollars,
    civilian_allocation_confidence,
    military_allocation_confidence,
    combined_allocation_confidence
FROM analysis.v_wa_federal_wage_allocation
WHERE fiscal_year IN (2018, 2019)
ORDER BY fiscal_year;


-- ================================================================================================
-- 7. ORIGINAL MEDICARE CONTROL
--
-- Retain the existing Original Medicare actual-payment control only.
-- Do not import the currently NOT_YET_AUTHORIZED Part C / Part D reconstruction.
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '7. ORIGINAL MEDICARE CONTROL'
\echo '===================================================================================================='

SELECT
    report_year,
    state_name,
    total_beneficiaries,
    original_medicare_beneficiaries,
    medicare_advantage_beneficiaries,
    actual_medicare_payments_dollars,
    standardized_medicare_payments_dollars
FROM reporting.v_medicare_expenditures_by_state_year
WHERE report_year IN (2018, 2019)
ORDER BY report_year;


-- ================================================================================================
-- 8. VA GDX CONTROL
--
-- Preserve the authoritative annual VA control established by the existing GDX pipeline.
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '8. VA GDX CONTROL'
\echo '===================================================================================================='

SELECT
    fiscal_year,
    COUNT(*) AS county_rows,
    SUM(va_gdx_expenditure_amount) AS washington_va_gdx_dollars
FROM va.v_washington_county_gdx_control_total
WHERE fiscal_year IN (2018, 2019)
GROUP BY fiscal_year
ORDER BY fiscal_year;


-- ================================================================================================
-- 9. MILITARY WAGE CONTROL
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '9. OMB / BEA MILITARY WAGE ALLOCATION'
\echo '===================================================================================================='

SELECT
    fiscal_year,
    budget_vintage,
    value_status,
    omb_accounting_measure,
    omb_scope,
    omb_military_wage_control_dollars,
    bea_wa_military_wages_dollars,
    bea_wa_share,
    bea_wa_share_percent,
    allocated_wa_military_wage_dollars,
    allocation_minus_bea_direct_dollars,
    allocation_to_bea_ratio
FROM bea.v_omb_military_wage_allocation
WHERE fiscal_year IN (2018, 2019)
ORDER BY fiscal_year;


-- ================================================================================================
-- 10. EXISTING PARTIAL BALANCE CONTROL
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '10. EXISTING PARTIAL BALANCE CONTROL'
\echo '===================================================================================================='

SELECT
    report_year,
    gross_collections_dollars,
    tracked_expenditures_dollars,
    partial_fiscal_balance_dollars,
    methodology_note
FROM reporting.v_washington_partial_fiscal_balance
WHERE report_year IN (2018, 2019)
ORDER BY report_year;


-- ================================================================================================
-- 11. COMPONENT AVAILABILITY BRIDGE
--
-- This is deliberately descriptive. It does NOT sum a candidate DRAFT-1 ledger.
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '11. COMPONENT AVAILABILITY BRIDGE'
\echo '===================================================================================================='

WITH years(fiscal_year) AS (
    VALUES (2018), (2019)
),
legacy AS (
    SELECT
        report_year AS fiscal_year,
        tracked_expenditures_dollars
    FROM reporting.v_washington_partial_fiscal_balance
    WHERE report_year IN (2018, 2019)
),
ssa AS (
    SELECT
        report_year AS fiscal_year,
        SUM(annualized_benefits_dollars) AS ssa_reporting_dollars
    FROM reporting.v_washington_ssa_summary
    WHERE report_year IN (2018, 2019)
    GROUP BY report_year
),
medicaid AS (
    SELECT
        fiscal_year,
        SUM(federal_expenditure_amount) AS medicaid_reporting_dollars,
        BOOL_AND(is_additive_to_fiscal_balance) AS medicaid_additive_flag
    FROM reporting.v_washington_medicaid_expenditures
    WHERE fiscal_year IN (2018, 2019)
    GROUP BY fiscal_year
),
chip AS (
    SELECT
        fiscal_year,
        SUM(federal_expenditure_amount) AS chip_reporting_dollars,
        BOOL_AND(is_additive_to_fiscal_balance) AS chip_additive_flag
    FROM reporting.v_washington_chip_expenditures
    WHERE fiscal_year IN (2018, 2019)
    GROUP BY fiscal_year
),
civilian_wages AS (
    SELECT
        fiscal_year,
        allocated_wa_civilian_wage_dollars
    FROM opm.v_omb_civilian_wage_allocation
    WHERE fiscal_year IN (2018, 2019)
),
military_wages AS (
    SELECT
        fiscal_year,
        allocated_wa_military_wage_dollars
    FROM bea.v_omb_military_wage_allocation
    WHERE fiscal_year IN (2018, 2019)
),
medicare AS (
    SELECT
        report_year AS fiscal_year,
        actual_medicare_payments_dollars
    FROM reporting.v_medicare_expenditures_by_state_year
    WHERE report_year IN (2018, 2019)
),
va AS (
    SELECT
        fiscal_year,
        SUM(va_gdx_expenditure_amount) AS va_gdx_dollars
    FROM va.v_washington_county_gdx_control_total
    WHERE fiscal_year IN (2018, 2019)
    GROUP BY fiscal_year
)
SELECT
    y.fiscal_year,
    l.tracked_expenditures_dollars AS legacy_tracked_expenditures_dollars,
    s.ssa_reporting_dollars,
    m.medicaid_reporting_dollars,
    m.medicaid_additive_flag,
    c.chip_reporting_dollars,
    c.chip_additive_flag,
    cw.allocated_wa_civilian_wage_dollars,
    mw.allocated_wa_military_wage_dollars,
    med.actual_medicare_payments_dollars,
    v.va_gdx_dollars
FROM years AS y
LEFT JOIN legacy AS l
    ON l.fiscal_year = y.fiscal_year
LEFT JOIN ssa AS s
    ON s.fiscal_year = y.fiscal_year
LEFT JOIN medicaid AS m
    ON m.fiscal_year = y.fiscal_year
LEFT JOIN chip AS c
    ON c.fiscal_year = y.fiscal_year
LEFT JOIN civilian_wages AS cw
    ON cw.fiscal_year = y.fiscal_year
LEFT JOIN military_wages AS mw
    ON mw.fiscal_year = y.fiscal_year
LEFT JOIN medicare AS med
    ON med.fiscal_year = y.fiscal_year
LEFT JOIN va AS v
    ON v.fiscal_year = y.fiscal_year
ORDER BY y.fiscal_year;


ROLLBACK;

\echo ''
\echo '===================================================================================================='
\echo 'ETL-195 COMPLETE'
\echo '===================================================================================================='
\echo 'READ ONLY'
\echo 'No database writes performed.'
\echo 'No accounting classifications changed.'
\echo 'No ledger inclusion decisions made.'
\echo 'No missing values inferred.'
\echo '===================================================================================================='