\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo '============================================================'
\echo 'ETL-221F - STATEWIDE EXPENDITURE ASSEMBLY INVENTORY'
\echo 'FY2018-FY2024'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

\echo ''
\echo '1. EXISTING ACCOUNTING AND CLASSIFICATION OBJECTS'

SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema IN (
    'analysis',
    'assistance',
    'reference',
    'reporting',
    'procurement',
    'usa',
    'va',
    'ssa',
    'cms',
    'omb',
    'opm',
    'bea',
    'rrb'
)
AND (
       table_name ILIKE '%classification%'
    OR table_name ILIKE '%policy%'
    OR table_name ILIKE '%mapping%'
    OR table_name ILIKE '%accounting%'
    OR table_name ILIKE '%reconcil%'
    OR table_name ILIKE '%ledger%'
    OR table_name ILIKE '%summary%'
    OR table_name ILIKE '%allocation%'
)
ORDER BY table_schema, table_name;

\echo ''
\echo '2. RELEVANT SOURCE AND CLASSIFICATION COLUMNS'

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema IN (
    'analysis',
    'assistance',
    'reference',
    'reporting',
    'procurement'
)
AND (
       table_name ILIKE '%classification%'
    OR table_name ILIKE '%policy%'
    OR table_name ILIKE '%mapping%'
    OR table_name ILIKE '%ledger%'
)
ORDER BY table_schema, table_name, ordinal_position;

\echo ''
\echo '3. EXISTING STATEWIDE REPORTING COMPONENTS'

SELECT
    report_year,
    agency_code,
    program_code,
    program_name,
    COUNT(*) AS component_rows
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
\echo '4. FEDERAL WAGE SOURCE COVERAGE'

SELECT
    fiscal_year,
    allocated_wa_civilian_wage_dollars,
    allocated_wa_military_wage_dollars,
    allocated_wa_total_federal_wage_dollars,
    combined_allocation_confidence
FROM analysis.v_wa_federal_wage_allocation
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year;

\echo ''
\echo '5. VA GDX SOURCE COVERAGE'

SELECT
    fiscal_year,
    COUNT(*) AS county_rows,
    SUM(va_gdx_expenditure_amount) AS state_total_dollars
FROM va.v_washington_county_gdx_control_total
WHERE fiscal_year BETWEEN 2018 AND 2024
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '6. SOURCE POLICY COVERAGE BY YEAR'

WITH years AS (
    SELECT generate_series(2018, 2024) AS fiscal_year
)
SELECT
    y.fiscal_year,
    p.inflow_family,
    p.ledger_treatment,
    COUNT(*) AS applicable_policy_rows,
    COUNT(DISTINCT p.inflow_subfamily) AS distinct_subfamilies
FROM years y
JOIN reference.federal_inflow_source_policy p
  ON y.fiscal_year BETWEEN
       p.valid_from_fiscal_year
       AND p.valid_through_fiscal_year
GROUP BY
    y.fiscal_year,
    p.inflow_family,
    p.ledger_treatment
ORDER BY
    y.fiscal_year,
    p.inflow_family,
    p.ledger_treatment;

\echo ''
\echo '7. EXISTING FEDERAL REVENUE CONTROL'

SELECT *
FROM reporting.v_washington_revenue_summary
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year;

\echo ''
\echo '8. EXISTING PARTIAL FISCAL BALANCE'

SELECT *
FROM reporting.v_washington_partial_fiscal_balance
ORDER BY 1;

ROLLBACK;