-- ETL-236A
-- Statewide accounting object inventory
-- READ ONLY: no database changes

BEGIN TRANSACTION READ ONLY;

SELECT
    v.schema_name,
    v.object_name,
    CASE
        WHEN c.oid IS NULL THEN 'NOT_FOUND'
        WHEN c.relkind = 'r' THEN 'TABLE'
        WHEN c.relkind = 'v' THEN 'VIEW'
        WHEN c.relkind = 'm' THEN 'MATERIALIZED_VIEW'
        WHEN c.relkind = 'p' THEN 'PARTITIONED_TABLE'
        WHEN c.relkind = 'f' THEN 'FOREIGN_TABLE'
        ELSE 'OTHER'
    END AS object_status
FROM (
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
) AS v(schema_name, object_name)
LEFT JOIN pg_namespace n
    ON n.nspname = v.schema_name
LEFT JOIN pg_class c
    ON c.relnamespace = n.oid
   AND c.relname = v.object_name
ORDER BY
    v.schema_name,
    v.object_name;

ROLLBACK;