
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-214A - ACCOUNTING ARCHITECTURE INVENTORY'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. DATABASE IDENTITY'
SELECT
    current_database() AS database_name,
    current_user AS database_user,
    current_setting('server_version') AS postgres_version,
    current_setting('transaction_read_only') AS read_only;

\echo ''
\echo '2. NON-SYSTEM SCHEMAS'
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name NOT IN
    ('information_schema', 'pg_catalog')
  AND schema_name NOT LIKE 'pg_toast%'
  AND schema_name NOT LIKE 'pg_temp_%'
ORDER BY schema_name;

\echo ''
\echo '3. ACCOUNTING / REPORTING OBJECT INVENTORY'
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
  AND n.nspname NOT IN
      ('pg_catalog','information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
  AND n.nspname NOT LIKE 'pg_temp_%'
  AND (
      n.nspname IN ('reporting','ledger','accounting')
      OR c.relname ~* (
          'ledger|balance|inflow|outflow|'
          || 'source_policy|source_control|'
          || 'reconcil|fiscal|expenditure|receipt'
      )
  )
ORDER BY n.nspname, c.relkind, c.relname;

\echo ''
\echo '4. COLUMNS OF ACCOUNTING / REPORTING OBJECTS'
SELECT
    cols.table_schema,
    cols.table_name,
    cols.ordinal_position,
    cols.column_name,
    cols.data_type
FROM information_schema.columns cols
WHERE cols.table_schema IN
    ('reporting','ledger','accounting')
   OR cols.table_name ~* (
       'ledger|balance|inflow|outflow|'
       || 'source_policy|source_control|'
       || 'reconcil'
   )
ORDER BY
    cols.table_schema,
    cols.table_name,
    cols.ordinal_position;

\echo ''
\echo '5. REPORTING VIEW DEFINITIONS'
SELECT
    schemaname,
    viewname,
    definition
FROM pg_catalog.pg_views
WHERE schemaname = 'reporting'
ORDER BY viewname;

\echo ''
\echo '6. REPORTING MATERIALIZED VIEWS'
SELECT
    schemaname,
    matviewname,
    ispopulated,
    definition
FROM pg_catalog.pg_matviews
WHERE schemaname = 'reporting'
ORDER BY matviewname;

ROLLBACK;

\echo ''
\echo 'ETL-214A COMPLETE - NO DATABASE WRITES'
