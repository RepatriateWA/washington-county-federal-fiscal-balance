
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '===================================================='
\echo 'ETL-216D - VA AND SSA ACCOUNTING READINESS'
\echo 'FY2018-FY2024 / READ ONLY'
\echo '===================================================='

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. VA SOURCE POLICY COVERAGE BY YEAR'

WITH years AS (
    SELECT generate_series(2018,2024) AS fiscal_year
)
SELECT
    y.fiscal_year,
    s.inflow_family,
    s.inflow_subfamily,
    s.accounting_measure,
    s.preferred_source,
    s.ledger_treatment,
    s.methodology_version
FROM years y
LEFT JOIN reference.federal_inflow_source_policy s
  ON s.inflow_family = 'VETERANS_AFFAIRS'
 AND (
     s.valid_from_fiscal_year IS NULL
     OR s.valid_from_fiscal_year <= y.fiscal_year
 )
 AND (
     s.valid_through_fiscal_year IS NULL
     OR s.valid_through_fiscal_year >= y.fiscal_year
 )
ORDER BY
    y.fiscal_year,
    s.inflow_subfamily,
    s.methodology_version;

\echo ''
\echo '2. VA GDX STATEWIDE COVERAGE'

SELECT
    fiscal_year,
    COUNT(DISTINCT county_id) AS county_count,
    SUM(va_gdx_expenditure_amount) AS amount
FROM va.v_washington_county_gdx_control_total
WHERE fiscal_year BETWEEN 2018 AND 2024
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '3. SSA SOURCE POLICY COVERAGE BY YEAR'

WITH years AS (
    SELECT generate_series(2018,2024) AS fiscal_year
)
SELECT
    y.fiscal_year,
    s.inflow_subfamily,
    s.accounting_measure,
    s.preferred_source,
    s.ledger_treatment,
    s.methodology_version
FROM years y
LEFT JOIN reference.federal_inflow_source_policy s
  ON s.inflow_family = 'SOCIAL_SECURITY'
 AND (
     s.valid_from_fiscal_year IS NULL
     OR s.valid_from_fiscal_year <= y.fiscal_year
 )
 AND (
     s.valid_through_fiscal_year IS NULL
     OR s.valid_through_fiscal_year >= y.fiscal_year
 )
ORDER BY y.fiscal_year, s.inflow_subfamily;

\echo ''
\echo '4. SSA SCHEMA OBJECT INVENTORY'

SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema IN ('ssa','reporting','analysis')
  AND (
      table_name ILIKE '%oasdi%'
      OR table_name ILIKE '%benefit%'
      OR table_name ILIKE '%payment%'
      OR table_name ILIKE '%ssa%'
  )
ORDER BY table_schema, table_name;

\echo ''
\echo '5. SSA RELEVANT COLUMN INVENTORY'

SELECT
    c.table_schema,
    c.table_name,
    c.ordinal_position,
    c.column_name,
    c.data_type
FROM information_schema.columns c
WHERE c.table_schema IN ('ssa','reporting','analysis')
  AND (
      c.table_name ILIKE '%oasdi%'
      OR c.table_name ILIKE '%benefit%'
      OR c.table_name ILIKE '%payment%'
      OR c.table_name ILIKE '%ssa%'
  )
ORDER BY
    c.table_schema,
    c.table_name,
    c.ordinal_position;

ROLLBACK;

\echo ''
\echo 'ETL-216D COMPLETE - READ ONLY'
