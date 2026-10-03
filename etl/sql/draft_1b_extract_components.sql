\echo ''
\echo '===================================================================================================='
\echo 'WCFFBP DRAFT 1B'
\echo 'STATEWIDE FISCAL-BALANCE COMPONENT EXTRACTION'
\echo 'READ ONLY'
\echo '===================================================================================================='
\echo ''

\set ON_ERROR_STOP on

BEGIN;


/*
====================================================================================================
1. EXISTING PARTIAL BALANCE

Contains:
    IRS gross collections
    SSA OASDI
    Original Medicare
    Medicaid

Does NOT yet contain:
    CHIP
    VA
    USAspending
    Medicare Advantage
    federal wages
    other expenditure streams
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. EXISTING PARTIAL FISCAL BALANCE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT *
FROM reporting.v_washington_partial_fiscal_balance
ORDER BY report_year;


/*
====================================================================================================
2. EXISTING TRACKED EXPENDITURE COMPONENTS

This decomposes the partial-balance expenditure total.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. TRACKED EXPENDITURE COMPONENTS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT *
FROM reporting.v_washington_tracked_expenditures
ORDER BY
    report_year,
    agency_code,
    program_code;


/*
====================================================================================================
3. SSA
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. SSA'
\echo '----------------------------------------------------------------------------------------------------'

SELECT *
FROM reporting.v_washington_ssa_summary
ORDER BY
    report_year,
    program_code;


/*
====================================================================================================
4. MEDICARE

No state filter needed for this diagnostic.
We will inspect what the existing reporting view actually contains.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. MEDICARE STATE-YEAR VIEW'
\echo '----------------------------------------------------------------------------------------------------'

SELECT *
FROM reporting.v_medicare_expenditures_by_state_year
ORDER BY
    report_year,
    state_id;


/*
====================================================================================================
5. MEDICAID
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. WASHINGTON MEDICAID'
\echo '----------------------------------------------------------------------------------------------------'

SELECT *
FROM reporting.v_washington_medicaid_expenditures
ORDER BY fiscal_year;


/*
====================================================================================================
6. CHIP
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. WASHINGTON CHIP'
\echo '----------------------------------------------------------------------------------------------------'

SELECT *
FROM reporting.v_washington_chip_expenditures
ORDER BY fiscal_year;


/*
====================================================================================================
7. FEDERAL WAGES
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. WASHINGTON FEDERAL WAGE ALLOCATION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    fiscal_year,

    allocated_wa_civilian_wage_dollars,

    allocated_wa_military_wage_dollars,

    allocated_wa_total_federal_wage_dollars,

    civilian_allocation_confidence,

    military_allocation_confidence,

    combined_allocation_confidence,

    civilian_value_status,

    military_value_status,

    certification_methodology_version

FROM analysis.v_wa_federal_wage_allocation

ORDER BY fiscal_year;


/*
====================================================================================================
8. VA GDX — AGGREGATE COUNTY CONTROL TO STATE-YEAR

The view is county-level.
For Draft 1 we need only the statewide annual control.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. VA GDX STATEWIDE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    fiscal_year,

    COUNT(DISTINCT county_id)
        AS county_count,

    ROUND(
        SUM(va_gdx_expenditure_amount)::numeric,
        2
    ) AS va_gdx_statewide_expenditure

FROM va.v_washington_county_gdx_control_total

GROUP BY fiscal_year

ORDER BY fiscal_year;


/*
====================================================================================================
9. PROCUREMENT — COLUMN INVENTORY

Do not yet assume transaction column names.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. PROCUREMENT TRANSACTION COLUMN INVENTORY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    ordinal_position,
    column_name,
    data_type

FROM information_schema.columns

WHERE table_schema = 'procurement'
  AND table_name = 'award_transaction'

ORDER BY ordinal_position;


/*
====================================================================================================
10. PROCUREMENT AWARD COLUMN INVENTORY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. PROCUREMENT AWARD COLUMN INVENTORY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    ordinal_position,
    column_name,
    data_type

FROM information_schema.columns

WHERE table_schema = 'procurement'
  AND table_name = 'award'

ORDER BY ordinal_position;


/*
====================================================================================================
11. IRS TAX CONTROL — REPRODUCE DIRECTLY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. IRS FEDERAL RECEIPTS CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    fiscal_year,
    gross_collections_dollars

FROM reporting.v_washington_revenue_summary

ORDER BY fiscal_year;


/*
====================================================================================================
12. CLOSURE
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'WCFFBP DRAFT 1B COMPONENT EXTRACTION COMPLETE'
\echo ''
\echo 'READ ONLY'
\echo 'No database writes.'
\echo 'No new accounting decisions.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;