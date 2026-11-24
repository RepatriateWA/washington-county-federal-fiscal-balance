\set ON_ERROR_STOP on

BEGIN READ ONLY;

SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    c.relkind AS object_type,
    pg_get_viewdef(c.oid, true) AS view_definition
FROM pg_class c
JOIN pg_namespace n
    ON n.oid = c.relnamespace
WHERE (n.nspname, c.relname) IN (
    ('reporting', 'v_washington_medicaid_expenditures'),
    ('reporting', 'v_washington_chip_expenditures'),
    ('chip', 'v_cms21_additive_expenditures')
)
AND c.relkind IN ('v', 'm')
ORDER BY n.nspname, c.relname;

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE (table_schema, table_name) IN (
    ('cms', 'medicaid_state_control_total'),
    ('reporting', 'v_washington_medicaid_expenditures'),
    ('reporting', 'v_washington_chip_expenditures'),
    ('chip', 'v_cms21_additive_expenditures')
)
ORDER BY table_schema, table_name, ordinal_position;

ROLLBACK;
