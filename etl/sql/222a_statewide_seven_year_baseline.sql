\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-222A - STATEWIDE SEVEN-YEAR ACCOUNTING BASELINE'
\echo 'FY2018-FY2024 - READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. REVENUE AND CURRENT PARTIAL EXPENDITURE BASELINE'

SELECT
    r.fiscal_year,
    r.gross_collections_dollars AS federal_revenue,
    p.tracked_expenditures_dollars AS currently_tracked_expenditures,
    p.partial_balance_dollars AS currently_reported_partial_balance
FROM reporting.v_washington_revenue_summary r
LEFT JOIN reporting.v_washington_partial_fiscal_balance p
    ON p.fiscal_year = r.fiscal_year
WHERE r.fiscal_year BETWEEN 2018 AND 2024
ORDER BY r.fiscal_year;

\echo ''
\echo '2. EXISTING ACCOUNTING AND REPORTING OBJECTS'

SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema IN (
    'reporting', 'analysis', 'cms', 'ssa', 'va',
    'irs', 'usa', 'assistance', 'reference'
)
AND (
    table_name ILIKE '%fiscal%'
    OR table_name ILIKE '%expenditure%'
    OR table_name ILIKE '%accounting%'
    OR table_name ILIKE '%ledger%'
    OR table_name ILIKE '%wage%'
    OR table_name ILIKE '%balance%'
)
ORDER BY table_schema, table_name;

\echo ''
\echo '3. STATEWIDE SOURCE-FAMILY VIEW DEFINITIONS'

SELECT
    schemaname,
    viewname,
    definition
FROM pg_views
WHERE (
    (schemaname = 'reporting'
     AND viewname IN (
         'v_washington_revenue_summary',
         'v_washington_tracked_expenditures',
         'v_washington_partial_fiscal_balance'
     ))
    OR (schemaname = 'va'
        AND viewname = 'v_washington_county_gdx_control_total')
    OR (schemaname = 'analysis'
        AND viewname = 'v_wa_federal_wage_allocation')
)
ORDER BY schemaname, viewname;

ROLLBACK;

\echo 'ETL-222A COMPLETE - NO DATABASE WRITES'