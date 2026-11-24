\set ON_ERROR_STOP on
\pset pager off

\echo 'ETL-222C - REMAINING EXPENDITURE FAMILY INVENTORY'
\echo 'READ ONLY - NO DATABASE WRITES'

BEGIN TRANSACTION READ ONLY;

SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    CASE c.relkind
        WHEN 'r' THEN 'TABLE'
        WHEN 'v' THEN 'VIEW'
        WHEN 'm' THEN 'MATERIALIZED VIEW'
        WHEN 'p' THEN 'PARTITIONED TABLE'
    END AS object_type
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN (
    'reporting', 'analysis', 'assistance',
    'procurement', 'usa', 'cms', 'ssa',
    'va', 'rrb', 'reference'
)
AND c.relkind IN ('r', 'v', 'm', 'p')
AND (
    c.relname ILIKE '%assistance%'
    OR c.relname ILIKE '%procurement%'
    OR c.relname ILIKE '%railroad%'
    OR c.relname ILIKE '%retirement%'
    OR c.relname ILIKE '%medicare%'
    OR c.relname ILIKE '%accounting%'
    OR c.relname ILIKE '%inflow%'
    OR c.relname ILIKE '%ledger%'
)
ORDER BY n.nspname, c.relname;

ROLLBACK;

\echo 'ETL-222C COMPLETE - NO DATABASE WRITES'