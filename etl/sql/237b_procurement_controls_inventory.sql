-- ETL-237B
-- Identify existing procurement attribution and overlap controls
-- READ ONLY

BEGIN TRANSACTION READ ONLY;

SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    CASE c.relkind
        WHEN 'r' THEN 'TABLE'
        WHEN 'v' THEN 'VIEW'
        WHEN 'm' THEN 'MATERIALIZED VIEW'
        WHEN 'p' THEN 'PARTITIONED TABLE'
        ELSE c.relkind::text
    END AS object_type
FROM pg_class c
JOIN pg_namespace n
  ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND c.relkind IN ('r', 'v', 'm', 'p')
  AND (
      c.relname ILIKE '%procurement%'
      OR c.relname ILIKE '%contract%'
      OR c.relname ILIKE '%geographic_attribution%'
      OR c.relname ILIKE '%source_policy%'
  )
ORDER BY n.nspname, c.relname;

ROLLBACK;