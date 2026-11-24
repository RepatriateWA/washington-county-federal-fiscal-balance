\pset pager off
\set ON_ERROR_STOP on

\echo ''
\echo '===================================================================================================='
\echo 'ETL-194 - DRAFT-1 2018-2019 ACCOUNTING BRIDGE v0.1'
\echo '===================================================================================================='
\echo 'READ ONLY - NO DATABASE WRITES'
\echo ''
\echo 'Purpose:'
\echo '  Inventory explicit WCFFBP controls for extending the statewide DRAFT-1 calculation'
\echo '  backward to FFY2018 and FFY2019.'
\echo ''
\echo 'IMPORTANT:'
\echo '  This script profiles existing database evidence only.'
\echo '  It does not authorize ledger inclusion.'
\echo '  It does not infer missing values.'
\echo '  It does not treat calendar year as federal fiscal year.'
\echo '  It does not change accounting policy.'
\echo ''

BEGIN;
SET TRANSACTION READ ONLY;

-- ================================================================================================
-- 1. EXISTING HISTORICAL PARTIAL BALANCE
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '1. EXISTING HISTORICAL PARTIAL BALANCE'
\echo '===================================================================================================='

SELECT
    report_year,
    gross_collections_dollars,
    tracked_expenditures_dollars,
    partial_fiscal_balance_dollars
FROM reporting.v_washington_partial_fiscal_balance
WHERE report_year IN (2018, 2019)
ORDER BY report_year;


-- ================================================================================================
-- 2. IRS STATE COLLECTIONS - WASHINGTON ROWS ONLY
--
-- Preserve tax-category detail. Do not sum categories here and do not infer that
-- every row is independently additive to the statewide receipts control.
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '2A. IRS STATE COLLECTIONS - WASHINGTON CATEGORY DETAIL'
\echo '===================================================================================================='

SELECT
    fiscal_year,
    state_id,
    state_name,
    tax_category,
    returns_filed,
    returns_filed_electronically,
    gross_collections_thousands,
    refunds_issued,
    refund_amount_thousands,
    source_file
FROM irs.state_collections
WHERE fiscal_year IN (2018, 2019)
  AND state_name = 'Washington'
ORDER BY
    fiscal_year,
    tax_category;


\echo ''
\echo '===================================================================================================='
\echo '2B. ESTABLISHED WASHINGTON GROSS-COLLECTION CONTROL'
\echo '===================================================================================================='

SELECT
    fiscal_year,
    gross_collections_thousands,
    gross_collections_dollars
FROM reporting.v_washington_revenue_summary
WHERE fiscal_year IN (2018, 2019)
ORDER BY fiscal_year;


-- ================================================================================================
-- 3. SSA BENEFIT-PAYMENT STRUCTURE
--
-- We intentionally show benefit-type IDs separately rather than summing everything and
-- accidentally combining OASDI and SSI or duplicating state/county controls.
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '3. SSA BENEFIT PAYMENT PROFILE'
\echo '===================================================================================================='

SELECT
    bp.report_year,
    bp.ssa_benefit_type_id,
    COUNT(*) AS observation_count,
    SUM(bp.monthly_benefits_thousands) AS monthly_benefits_thousands_sum,
    SUM(bp.annual_benefits_thousands) AS annual_benefits_thousands_sum
FROM ssa.benefit_payments AS bp
WHERE bp.report_year IN (2018, 2019)
GROUP BY
    bp.report_year,
    bp.ssa_benefit_type_id
ORDER BY
    bp.report_year,
    bp.ssa_benefit_type_id;

\echo ''
\echo 'SSA BENEFIT TYPE LOOKUP'
SELECT *
FROM reference.ssa_benefit_type
ORDER BY ssa_benefit_type_id;


-- ================================================================================================
-- 4. VA GDX - AUTHORITATIVE WASHINGTON CONTROL
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '4. VA GDX WASHINGTON CONTROL'
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
-- 5. BEA / OMB FEDERAL WAGE ALLOCATION OBJECTS
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '5A. BEA / OMB MILITARY WAGE ALLOCATION'
\echo '===================================================================================================='

SELECT *
FROM bea.v_omb_military_wage_allocation
WHERE fiscal_year IN (2018, 2019)
ORDER BY fiscal_year;

\echo ''
\echo '===================================================================================================='
\echo '5B. BEA OBJECT INVENTORY'
\echo '===================================================================================================='

SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'bea'
ORDER BY table_name, ordinal_position;


-- ================================================================================================
-- 6. MEDICARE CORE STATE-YEAR
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '6. MEDICARE CORE STATE-YEAR'
\echo '===================================================================================================='

SELECT *
FROM cms.medicare_core_state_year
WHERE calendar_year IN (2018, 2019)
ORDER BY calendar_year;


-- ================================================================================================
-- 7. MEDICARE GEOGRAPHIC WASHINGTON STATE CONTROL
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '7. MEDICARE STATE-YEAR REPORTING CONTROL'
\echo '===================================================================================================='

SELECT *
FROM reporting.v_medicare_expenditures_by_state_year
WHERE report_year IN (2018, 2019)
ORDER BY report_year;


-- ================================================================================================
-- 8. CHIP OBJECTS AND TARGET-YEAR OBSERVATIONS
--
-- First expose the schema. We do not guess which CHIP field is the authoritative
-- accounting control.
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '8A. CHIP SCHEMA'
\echo '===================================================================================================='

SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'chip'
ORDER BY table_name, ordinal_position;

\echo ''
\echo '===================================================================================================='
\echo '8B. CHIP TABLE ROW COUNTS'
\echo '===================================================================================================='

SELECT
    schemaname,
    relname AS table_name,
    n_live_tup AS estimated_rows
FROM pg_stat_user_tables
WHERE schemaname = 'chip'
ORDER BY relname;


-- ================================================================================================
-- 9. EXPENDITURE SCHEMA
--
-- This may expose Medicaid or other previously tracked controls without making
-- assumptions about column semantics.
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '9. EXPENDITURE SCHEMA'
\echo '===================================================================================================='

SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'expenditure'
ORDER BY table_name, ordinal_position;


-- ================================================================================================
-- 10. USAspending ASSISTANCE
--
-- v0.2 showed no explicit 2018/2019 row in the statewide assistance-by-year view.
-- Confirm that directly rather than deriving anything from raw transactions.
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '10. STATEWIDE ASSISTANCE BY YEAR'
\echo '===================================================================================================='

SELECT *
FROM analysis.v_statewide_assistance_by_year
WHERE fiscal_year IN (2018, 2019)
ORDER BY fiscal_year;


-- ================================================================================================
-- 11. PROCUREMENT
--
-- Presence here is provenance/discovery only. It is NOT automatically additive,
-- especially where authoritative program controls overlap.
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '11. PROCUREMENT PROFILE'
\echo '===================================================================================================='

SELECT
    fiscal_year,
    COUNT(*) AS transaction_count,
    SUM(federal_action_obligation) AS federal_action_obligation_dollars
FROM procurement.award_transaction
WHERE fiscal_year IN (2018, 2019)
GROUP BY fiscal_year
ORDER BY fiscal_year;


-- ================================================================================================
-- 12. OPM OBJECT INVENTORY
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '12. OPM OBJECT INVENTORY'
\echo '===================================================================================================='

SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'opm'
ORDER BY table_name, ordinal_position;


-- ================================================================================================
-- 13. REPORTING OBJECTS
--
-- This tells us whether another already-built reporting view contains useful statewide
-- controls that should be interrogated in the next pass.
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '13. REPORTING SCHEMA INVENTORY'
\echo '===================================================================================================='

SELECT
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'reporting'
ORDER BY table_name, ordinal_position;


-- ================================================================================================
-- 14. ANALYSIS OBJECTS
-- ================================================================================================

\echo ''
\echo '===================================================================================================='
\echo '14. ANALYSIS SCHEMA INVENTORY'
\echo '===================================================================================================='

SELECT
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'analysis'
ORDER BY table_name, ordinal_position;


ROLLBACK;

\echo ''
\echo '===================================================================================================='
\echo 'ETL-194 COMPLETE'
\echo '===================================================================================================='
\echo 'READ ONLY'
\echo 'No database writes performed.'
\echo 'No accounting classifications changed.'
\echo 'No ledger inclusion decisions made.'
\echo '===================================================================================================='