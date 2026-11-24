
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '======================================================'
\echo 'ETL-216E - VA / SSA SOURCE EVIDENCE'
\echo 'FY2018-FY2024 / READ ONLY'
\echo '======================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. SSA ANNUALIZATION TEST BY YEAR AND BENEFIT TYPE'

SELECT
    report_year,
    benefit_type,
    COUNT(*) AS source_rows,
    COUNT(DISTINCT county_id) AS distinct_counties,
    SUM(monthly_benefits_thousands) AS monthly_thousands,
    SUM(annual_benefits_thousands) AS annual_thousands,
    SUM(annual_benefits_thousands)
      - 12 * SUM(monthly_benefits_thousands)
        AS annual_minus_twelve_months,
    COUNT(*) FILTER (
        WHERE monthly_benefits_thousands IS NULL
           OR annual_benefits_thousands IS NULL
    ) AS null_amount_rows,
    COUNT(*) FILTER (
        WHERE monthly_benefits_thousands IS NOT NULL
          AND annual_benefits_thousands IS NOT NULL
          AND annual_benefits_thousands
              <> 12 * monthly_benefits_thousands
    ) AS nonmatching_rows
FROM ssa.benefit_payments
WHERE report_year BETWEEN 2018 AND 2024
GROUP BY report_year, benefit_type
ORDER BY report_year, benefit_type;

\echo ''
\echo '2. SSA SOURCE FILE AND TABLE PROVENANCE'

SELECT
    report_year,
    source_file,
    source_table,
    COUNT(*) AS rows,
    COUNT(DISTINCT benefit_type) AS benefit_types,
    COUNT(DISTINCT county_id) AS counties
FROM ssa.benefit_payments
WHERE report_year BETWEEN 2018 AND 2024
GROUP BY report_year, source_file, source_table
ORDER BY report_year, source_file, source_table;

\echo ''
\echo '3. SSA ANNUALIZATION EXCEPTIONS'

SELECT
    report_year,
    state_id,
    county_id,
    county_name,
    benefit_type,
    monthly_benefits_thousands,
    annual_benefits_thousands,
    source_file,
    source_table
FROM ssa.benefit_payments
WHERE report_year BETWEEN 2018 AND 2024
  AND (
      monthly_benefits_thousands IS NULL
      OR annual_benefits_thousands IS NULL
      OR annual_benefits_thousands
         <> 12 * monthly_benefits_thousands
  )
ORDER BY report_year, county_id, benefit_type
LIMIT 100;

\echo ''
\echo '4. VA TOTAL-EXPENDITURE SOURCE POLICIES'

SELECT
    federal_inflow_source_policy_id,
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    source_selection_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE inflow_family = 'VETERANS_AFFAIRS'
  AND inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
ORDER BY valid_from_fiscal_year, methodology_version;

\echo ''
\echo '5. VA SOURCE POLICY INVENTORY, ALL FAMILIES'

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
WHERE preferred_source = 'VA_GDX'
   OR allocation_source = 'VA_GDX'
ORDER BY
    inflow_family,
    inflow_subfamily,
    valid_from_fiscal_year,
    methodology_version;

\echo ''
\echo '6. VA ACCOUNTING OBJECT INVENTORY'

SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema IN ('va','reporting','analysis')
  AND (
      table_name ILIKE '%veteran%'
      OR table_name ILIKE '%gdx%'
      OR table_name ILIKE '%va_expenditure%'
  )
ORDER BY table_schema, table_name;

ROLLBACK;

\echo ''
\echo 'ETL-216E COMPLETE - READ ONLY'
