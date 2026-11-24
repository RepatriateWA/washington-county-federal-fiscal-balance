-- ETL-202A.1
-- Federal fiscal coverage database discovery
-- READ ONLY

\pset pager off
\set ON_ERROR_STOP on

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT
    current_database() AS database_name,
    current_user AS database_user,
    current_setting('server_version') AS pg_version,
    CURRENT_TIMESTAMP AS inspected_at;

-- 1. Schema inventory
SELECT
    n.nspname AS schema_name,
    COUNT(*) FILTER (WHERE c.relkind IN ('r','p')) AS tables,
    COUNT(*) FILTER (WHERE c.relkind = 'v') AS views,
    COUNT(*) FILTER (WHERE c.relkind = 'm') AS materialized_views
FROM pg_namespace AS n
JOIN pg_class AS c ON c.relnamespace = n.oid
WHERE n.nspname <> 'information_schema'
  AND LEFT(n.nspname, 3) <> 'pg_'
GROUP BY n.nspname
ORDER BY n.nspname;

-- 2. All user tables and views
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    CASE c.relkind
        WHEN 'r' THEN 'TABLE'
        WHEN 'p' THEN 'PARTITIONED TABLE'
        WHEN 'v' THEN 'VIEW'
        WHEN 'm' THEN 'MATERIALIZED VIEW'
        WHEN 'f' THEN 'FOREIGN TABLE'
    END AS relation_type,
    CASE
        WHEN c.relkind IN ('r','m')
        THEN GREATEST(c.reltuples::bigint, 0)
        ELSE NULL
    END AS estimated_rows,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS relation_size
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','p','v','m','f')
  AND n.nspname <> 'information_schema'
  AND LEFT(n.nspname, 3) <> 'pg_'
ORDER BY n.nspname, c.relname;

-- 3. Candidate fiscal and policy relations
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    COUNT(a.attnum) AS column_count
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
LEFT JOIN pg_attribute AS a
  ON a.attrelid = c.oid
 AND a.attnum > 0
 AND NOT a.attisdropped
WHERE c.relkind IN ('r','p','v','m','f')
  AND n.nspname <> 'information_schema'
  AND LEFT(n.nspname, 3) <> 'pg_'
  AND (
      n.nspname ~* 'irs|tax|treasury|ssa|cms|medicare|medicaid|va|bea|omb|budget|spend|assistance|procure|fiscal|ledger|control|recon|policy'
      OR
      c.relname ~* 'irs|tax|treasury|ssa|cms|medicare|medicaid|va|bea|omb|budget|spend|assistance|procure|fiscal|ledger|control|recon|policy|source|receipt|payment|expenditure|allocation'
  )
GROUP BY n.nspname, c.relname
ORDER BY n.nspname, c.relname;

-- 4. Candidate year, geography, amount, and policy columns
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    a.attname AS column_name,
    format_type(a.atttypid, a.atttypmod) AS data_type
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
JOIN pg_attribute AS a
  ON a.attrelid = c.oid
 AND a.attnum > 0
 AND NOT a.attisdropped
WHERE c.relkind IN ('r','p','v','m','f')
  AND n.nspname <> 'information_schema'
  AND LEFT(n.nspname, 3) <> 'pg_'
  AND a.attname ~* 'year|fiscal|date|period|state|county|fips|geograph|amount|dollar|value|obligat|outlay|receipt|revenue|payment|spend|expend|policy|status|source|control|overlap|inclusion'
ORDER BY n.nspname, c.relname, a.attnum;

ROLLBACK;
