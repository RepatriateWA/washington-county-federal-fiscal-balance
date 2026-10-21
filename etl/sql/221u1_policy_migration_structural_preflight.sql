\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo 'ETL-221U1 - POLICY MIGRATION STRUCTURAL PREFLIGHT'

SELECT
    conname,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid =
    'reference.federal_inflow_program_policy_mapping'::regclass
ORDER BY conname;

SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'reference'
  AND tablename = 'federal_inflow_program_policy_mapping'
ORDER BY indexname;

SELECT
    resolved_accounting_disposition,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    COUNT(*) AS policy_rows
FROM reference.federal_inflow_program_policy_mapping
WHERE source_system = 'USASPENDING_ASSISTANCE'
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

ROLLBACK;