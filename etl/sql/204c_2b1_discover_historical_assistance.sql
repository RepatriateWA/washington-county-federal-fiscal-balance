
/*
ETL-204C-2B.1
HISTORICAL ASSISTANCE DATABASE OBJECT DISCOVERY

READ ONLY — NO DATABASE WRITES
*/

\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo '======================================================'
\echo 'HISTORICAL ASSISTANCE OBJECT DISCOVERY'
\echo '======================================================'

-- 1. Find candidate tables, views, and materialized views

SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    CASE c.relkind
        WHEN 'r' THEN 'TABLE'
        WHEN 'p' THEN 'PARTITIONED TABLE'
        WHEN 'v' THEN 'VIEW'
        WHEN 'm' THEN 'MATERIALIZED VIEW'
        ELSE c.relkind::text
    END AS object_type
FROM pg_class c
JOIN pg_namespace n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p', 'v', 'm')
  AND n.nspname NOT IN
      ('pg_catalog', 'information_schema')
  AND (
      c.relname ILIKE '%assistance%'
      OR c.relname ILIKE '%historical%'
      OR c.relname ILIKE '%ledger%'
  )
ORDER BY n.nspname, c.relname;


-- 2. Find candidate fiscal-year and transaction columns

\echo ''
\echo 'CANDIDATE DATE / FISCAL YEAR / PROGRAM COLUMNS'

SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema NOT IN
      ('pg_catalog', 'information_schema')
  AND (
      table_name ILIKE '%assistance%'
      OR table_name ILIKE '%historical%'
      OR table_name ILIKE '%ledger%'
  )
  AND (
      column_name ILIKE '%fiscal_year%'
      OR column_name ILIKE '%action_date%'
      OR column_name ILIKE '%cfda%'
      OR column_name ILIKE '%program_code%'
      OR column_name ILIKE '%load_batch%'
      OR column_name ILIKE '%source_row%'
  )
ORDER BY
    table_schema,
    table_name,
    ordinal_position;


-- 3. Inspect the definition of the certified assistance view

\echo ''
\echo 'CERTIFIED ASSISTANCE VIEW DEFINITION'

SELECT pg_get_viewdef(
    'analysis.v_certified_assistance_ledger'::regclass,
    true
) AS view_definition;

COMMIT;

\echo ''
\echo 'DISCOVERY COMPLETE — READ ONLY'
