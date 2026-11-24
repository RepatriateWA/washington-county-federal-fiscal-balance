-- ETL-236B
-- Statewide accounting column inventory
-- READ ONLY: no database modifications

BEGIN TRANSACTION READ ONLY;

WITH targets(schema_name, object_name) AS (
    VALUES
    ('reporting', 'v_washington_revenue_summary'),
    ('reporting', 'v_washington_ssa_summary'),
    ('reporting', 'v_washington_medicaid_expenditures'),
    ('reporting', 'v_washington_chip_expenditures'),
    ('cms', 'medicare_core_state_year'),
    ('va', 'v_washington_county_gdx_control_total'),
    ('opm', 'v_omb_civilian_wage_allocation'),
    ('bea', 'v_omb_military_wage_allocation'),
    ('analysis', 'v_certified_assistance_ledger'),
    ('procurement', 'award_transaction'),
    ('reference', 'federal_inflow_award_classification'),
    ('reference', 'federal_inflow_program_policy_mapping')
)
SELECT
    t.schema_name,
    t.object_name,
    a.attnum AS column_position,
    a.attname AS column_name,
    format_type(a.atttypid, a.atttypmod) AS data_type
FROM targets t
JOIN pg_namespace n
    ON n.nspname = t.schema_name
JOIN pg_class c
    ON c.relnamespace = n.oid
   AND c.relname = t.object_name
JOIN pg_attribute a
    ON a.attrelid = c.oid
   AND a.attnum > 0
   AND NOT a.attisdropped
ORDER BY
    t.schema_name,
    t.object_name,
    a.attnum;

ROLLBACK;