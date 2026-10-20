
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '======================================================'
\echo 'ETL-216G - VA GDX COMPONENT SCHEMA AND SOURCE PROFILE'
\echo 'FY2020-FY2023 / READ ONLY'
\echo '======================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. VA GDX SOURCE TABLE COLUMNS'

SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'va'
  AND table_name IN (
      'gdx_county_expenditure',
      'gdx_county_metric',
      'gdx_expenditure_category',
      'gdx_load_batch'
  )
ORDER BY table_name, ordinal_position;

\echo ''
\echo '2. VA GDX OBJECT DEFINITIONS'

SELECT
    schemaname,
    viewname,
    definition
FROM pg_views
WHERE schemaname = 'va'
  AND viewname = 'v_washington_county_gdx_control_total';

\echo ''
\echo '3. VA GDX SOURCE CONSTRAINTS'

SELECT
    con.conrelid::regclass AS table_name,
    con.conname AS constraint_name,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint con
WHERE con.conrelid IN (
    'va.gdx_county_expenditure'::regclass,
    'va.gdx_county_metric'::regclass,
    'va.gdx_expenditure_category'::regclass,
    'va.gdx_load_batch'::regclass
)
ORDER BY table_name, constraint_name;

\echo ''
\echo '4. TARGET YEAR STATEWIDE CONTROL TOTALS'

SELECT
    fiscal_year,
    COUNT(*) AS county_rows,
    COUNT(DISTINCT county_id) AS distinct_counties,
    SUM(va_gdx_expenditure_amount) AS statewide_dollars
FROM va.v_washington_county_gdx_control_total
WHERE fiscal_year BETWEEN 2020 AND 2023
GROUP BY fiscal_year
ORDER BY fiscal_year;

ROLLBACK;

\echo ''
\echo 'ETL-216G COMPLETE - READ ONLY'
