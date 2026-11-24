\pset pager off
\echo 'ETL-240A2H8: AL 10.561 reconciliation preflight'

BEGIN TRANSACTION READ ONLY;

SELECT
    table_schema,
    table_name,
    column_name
FROM information_schema.columns
WHERE
    (
        table_name ILIKE '%assistance%'
        OR table_name ILIKE '%obligation%'
    )
    AND (
        column_name ILIKE '%program%'
        OR column_name ILIKE '%listing%'
        OR column_name ILIKE '%amount%'
        OR column_name ILIKE '%fiscal_year%'
        OR column_name ILIKE '%year%'
    )
ORDER BY table_schema, table_name, ordinal_position;

ROLLBACK;
