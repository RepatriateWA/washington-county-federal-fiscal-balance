\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo '============================================================'
\echo 'ETL-221D - FEDERAL WAGE OVERLAP AND AUTHORIZATION PREFLIGHT'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

\echo ''
\echo '1. EXISTING FEDERAL WAGE SOURCE POLICIES'

SELECT
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE inflow_family = 'FEDERAL_WAGES'
ORDER BY inflow_subfamily, valid_from_fiscal_year;

\echo ''
\echo '2. OTHER FEDERAL INFLOW SOURCE POLICIES'

SELECT
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    ledger_treatment,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE inflow_family <> 'FEDERAL_WAGES'
  AND valid_through_fiscal_year >= 2018
  AND valid_from_fiscal_year <= 2024
ORDER BY inflow_family, inflow_subfamily, valid_from_fiscal_year;

\echo ''
\echo '3. CURRENT REPORTING COMPONENTS'

SELECT
    agency_code,
    program_code,
    program_name,
    COUNT(*) AS reporting_rows,
    MIN(report_year) AS first_year,
    MAX(report_year) AS last_year
FROM reporting.v_washington_tracked_expenditures
WHERE report_year BETWEEN 2018 AND 2024
GROUP BY agency_code, program_code, program_name
ORDER BY agency_code, program_code;

\echo ''
\echo '4. CERTIFIED WAGE ALLOCATIONS'

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
\echo '5. WAGE ALLOCATION ARITHMETIC'

SELECT
    fiscal_year,
    allocated_wa_total_federal_wage_dollars
      - allocated_wa_civilian_wage_dollars
      - allocated_wa_military_wage_dollars
        AS reconciliation_difference_dollars
FROM analysis.v_wa_federal_wage_allocation
WHERE fiscal_year BETWEEN 2018 AND 2024
ORDER BY fiscal_year;

\echo ''
\echo '6. DATABASE OBJECTS RELEVANT TO WAGE OVERLAP'

SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema IN (
    'analysis',
    'reference',
    'reporting',
    'va',
    'usa',
    'omb',
    'opm',
    'bea'
)
AND (
       table_name ILIKE '%wage%'
    OR table_name ILIKE '%overlap%'
    OR table_name ILIKE '%ledger%'
    OR table_name ILIKE '%expenditure%'
    OR table_name ILIKE '%procurement%'
)
ORDER BY table_schema, table_name;

ROLLBACK;