-- ETL-236F
-- Identify existing USAspending reconciliation columns
-- READ ONLY

BEGIN TRANSACTION READ ONLY;

WITH targets(schema_name, object_name) AS (
    VALUES
        ('analysis', 'v_assistance_transaction_observation_ledger'),
        ('analysis', 'v_wa_funding_decomposition_reconciliation'),
        ('analysis', 'v_wa_obligation_reconciliation'),
        ('reference', 'federal_inflow_program_classification'),
        ('reference', 'federal_inflow_source_policy')
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
WHERE a.attnum > 0
  AND NOT a.attisdropped
ORDER BY
    t.schema_name,
    t.object_name,
    a.attnum;

ROLLBACK;