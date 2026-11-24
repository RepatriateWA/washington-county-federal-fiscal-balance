-- ETL-236E
-- USAspending policy linkage and existing reconciliation views
-- READ ONLY

BEGIN TRANSACTION READ ONLY;

-- 1. Existing assistance, overlap, and reconciliation views.
SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    CASE c.relkind
        WHEN 'v' THEN 'VIEW'
        WHEN 'm' THEN 'MATERIALIZED_VIEW'
        WHEN 'r' THEN 'TABLE'
        ELSE c.relkind::text
    END AS object_type
FROM pg_class c
JOIN pg_namespace n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('v', 'm', 'r')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND (
      c.relname ILIKE '%assistance%ledger%'
      OR c.relname ILIKE '%overlap%'
      OR c.relname ILIKE '%disposition%'
      OR c.relname ILIKE '%source%policy%'
      OR c.relname ILIKE '%federal%inflow%'
      OR c.relname ILIKE '%reconciliation%'
  )
ORDER BY n.nspname, c.relname;

-- 2. Definitions of the two classification tables.
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    a.attnum AS column_position,
    a.attname AS column_name,
    format_type(a.atttypid, a.atttypmod) AS data_type
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid
WHERE n.nspname = 'reference'
  AND c.relname IN (
      'federal_inflow_award_classification',
      'federal_inflow_program_policy_mapping'
  )
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY c.relname, a.attnum;

-- 3. Program policy classifications with program codes.
SELECT
    source_program_code,
    resolved_accounting_disposition,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    methodology_version
FROM reference.federal_inflow_program_policy_mapping
WHERE source_system = 'USASPENDING_ASSISTANCE'
ORDER BY source_program_code, valid_from_fiscal_year;

-- 4. Award-level classifications summarized by program.
SELECT
    source_program_code,
    inflow_family,
    accounting_disposition,
    COUNT(*) AS classification_rows
FROM reference.federal_inflow_award_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
GROUP BY
    source_program_code,
    inflow_family,
    accounting_disposition
ORDER BY
    source_program_code,
    inflow_family,
    accounting_disposition;

ROLLBACK;