BEGIN TRANSACTION READ ONLY;

SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    CASE c.relkind
        WHEN 'v' THEN 'VIEW'
        WHEN 'm' THEN 'MATERIALIZED VIEW'
        WHEN 'r' THEN 'TABLE'
        WHEN 'p' THEN 'PARTITIONED TABLE'
    END AS object_type,
    COALESCE(s.n_live_tup, 0) AS estimated_table_rows
FROM pg_class c
JOIN pg_namespace n
    ON n.oid = c.relnamespace
LEFT JOIN pg_stat_user_tables s
    ON s.relid = c.oid
WHERE n.nspname IN (
    'reporting', 'analysis', 'irs', 'ssa',
    'va', 'cms', 'omb', 'bea', 'opm',
    'procurement', 'assistance', 'reference'
)
AND c.relkind IN ('v', 'm', 'r', 'p')
AND (
    n.nspname IN ('reporting', 'analysis')
    OR c.relname ~* 'summary|control|balance|ledger|policy|allocation|payment|expenditure|collection|overlap|certif'
)
ORDER BY n.nspname, c.relname;

COMMIT;