
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-214E - ASSISTANCE LEDGER BRIDGE INVENTORY'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. ASSISTANCE AND RAILROAD ACCOUNTING OBJECTS'

SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    CASE c.relkind
        WHEN 'r' THEN 'TABLE'
        WHEN 'p' THEN 'PARTITIONED TABLE'
        WHEN 'v' THEN 'VIEW'
        WHEN 'm' THEN 'MATERIALIZED VIEW'
    END AS object_type
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','p','v','m')
  AND n.nspname NOT IN ('pg_catalog','information_schema')
  AND (
      n.nspname IN ('assistance','rrb','railroad')
      OR c.relname ~* (
          'assistance.*(policy|classif|mapping|ledger|bridge)'
          || '|(policy|classif|mapping|ledger|bridge).*assistance'
          || '|railroad|retirement'
      )
  )
ORDER BY n.nspname, c.relname;

\echo ''
\echo '2. ACCOUNTING CLASSIFICATION COLUMNS'

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE (
    table_name ~* 'policy|classification|mapping|ledger|bridge'
    AND table_schema IN ('analysis','assistance','reference')
)
ORDER BY table_schema, table_name, ordinal_position;

\echo ''
\echo '3. HISTORICAL RAILROAD RETIREMENT POLICIES'

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
WHERE inflow_family ~* 'RAILROAD'
ORDER BY inflow_family, inflow_subfamily,
         valid_from_fiscal_year;

ROLLBACK;

\echo 'ETL-214E COMPLETE - NO DATABASE WRITES'
