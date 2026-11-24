
\set ON_ERROR_STOP on
\pset pager off

\echo '=========================================================='
\echo 'ETL-214C - DRAFT-1 ACCOUNTING SOURCE INVENTORY'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '=========================================================='

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. RELEVANT ACCOUNTING SOURCE OBJECTS'

SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    CASE c.relkind
        WHEN 'r' THEN 'TABLE'
        WHEN 'p' THEN 'PARTITIONED TABLE'
        WHEN 'v' THEN 'VIEW'
        WHEN 'm' THEN 'MATERIALIZED VIEW'
        WHEN 'f' THEN 'FOREIGN TABLE'
    END AS object_type
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','p','v','m','f')
  AND n.nspname IN (
      'analysis','analytics','assistance',
      'bea','cms','expenditure','irs',
      'omb','procurement','reporting',
      'ssa','va'
  )
  AND (
      c.relname ~* (
          'wage|compensation|medicare_core|'
          || 'gdx|railroad|rrb|certified_assistance|'
          || 'fiscal_balance|receipt|'
          || 'accounting|allocation'
      )
  )
ORDER BY n.nspname, c.relname;

\echo ''
\echo '2. KEY SOURCE VIEW AND TABLE COLUMNS'

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE
    (table_schema = 'analysis'
     AND table_name = 'v_wa_federal_wage_allocation')
 OR (table_schema = 'cms'
     AND table_name = 'medicare_core_state_year')
 OR (table_schema = 'va'
     AND table_name = 'v_washington_county_gdx_control_total')
 OR (table_schema = 'analysis'
     AND table_name = 'v_certified_assistance_ledger')
 OR (table_schema = 'reporting'
     AND table_name = 'v_washington_tracked_expenditures')
ORDER BY table_schema, table_name, ordinal_position;

\echo ''
\echo '3. ACCOUNTING POLICY COVERAGE'

SELECT
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    ledger_treatment,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    methodology_version
FROM reference.federal_inflow_source_policy
WHERE valid_through_fiscal_year >= 2018
  AND valid_from_fiscal_year <= 2025
ORDER BY inflow_family,
         inflow_subfamily,
         valid_from_fiscal_year;

\echo ''
\echo '4. EXISTING REPORTED PROGRAM COVERAGE'

SELECT
    agency_code,
    program_code,
    MIN(report_year) AS first_year,
    MAX(report_year) AS last_year,
    COUNT(DISTINCT report_year) AS years_present
FROM reporting.v_washington_tracked_expenditures
WHERE report_year BETWEEN 2018 AND 2025
GROUP BY agency_code, program_code
ORDER BY agency_code, program_code;

ROLLBACK;

\echo 'ETL-214C COMPLETE - NO DATABASE WRITES'
