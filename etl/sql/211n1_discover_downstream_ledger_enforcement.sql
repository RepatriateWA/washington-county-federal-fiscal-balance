
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-211N1 - DOWNSTREAM LEDGER ENFORCEMENT DISCOVERY'
\echo 'FY2018-FY2019 VA ASSISTANCE'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- ============================================================
-- 1. INVENTORY LEDGER AND ACCOUNTING OBJECTS
-- ============================================================

\echo ''
\echo '1. RELEVANT DATABASE OBJECTS'

SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    CASE c.relkind
        WHEN 'r' THEN 'TABLE'
        WHEN 'p' THEN 'PARTITIONED TABLE'
        WHEN 'v' THEN 'VIEW'
        WHEN 'm' THEN 'MATERIALIZED VIEW'
        ELSE c.relkind::text
    END AS object_type
FROM pg_class c
JOIN pg_namespace n
  ON n.oid = c.relnamespace
WHERE n.nspname NOT IN (
    'pg_catalog',
    'information_schema'
)
  AND c.relkind IN ('r', 'p', 'v', 'm')
  AND (
      c.relname ILIKE '%ledger%'
      OR c.relname ILIKE '%accounting%'
      OR c.relname ILIKE '%inflow%'
      OR c.relname ILIKE '%disposition%'
      OR c.relname ILIKE '%balance%'
  )
ORDER BY n.nspname, c.relname;

-- ============================================================
-- 2. IDENTIFY VIEWS REFERENCING POLICY OR CLASSIFICATION
-- ============================================================

\echo ''
\echo '2. VIEW DEFINITIONS REFERENCING POLICY TABLES'

SELECT
    schemaname,
    viewname,
    definition
FROM pg_views
WHERE schemaname NOT IN (
    'pg_catalog',
    'information_schema'
)
  AND (
      definition ILIKE '%federal_inflow_program_policy_mapping%'
      OR definition ILIKE '%federal_inflow_source_policy%'
      OR definition ILIKE '%resolved_accounting_disposition%'
      OR definition ILIKE '%EXCLUDE_DUPLICATE%'
  )
ORDER BY schemaname, viewname;

-- ============================================================
-- 3. IDENTIFY LEDGER VIEW DEFINITIONS
-- ============================================================

\echo ''
\echo '3. LEDGER VIEW DEFINITIONS'

SELECT
    schemaname,
    viewname,
    definition
FROM pg_views
WHERE schemaname NOT IN (
    'pg_catalog',
    'information_schema'
)
  AND (
      viewname ILIKE '%ledger%'
      OR viewname ILIKE '%balance%'
  )
ORDER BY schemaname, viewname;

-- ============================================================
-- 4. FIND ACCOUNTING RESOLUTION COLUMNS
-- ============================================================

\echo ''
\echo '4. ACCOUNTING AND LEDGER COLUMNS'

SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema NOT IN (
    'pg_catalog',
    'information_schema'
)
  AND (
      column_name ILIKE '%disposition%'
      OR column_name ILIKE '%ledger%'
      OR column_name ILIKE '%policy%'
      OR column_name ILIKE '%additive%'
      OR column_name ILIKE '%accounting%'
      OR column_name ILIKE '%included%'
  )
ORDER BY table_schema, table_name, ordinal_position;

-- ============================================================
-- 5. VERIFY HISTORICAL MEDICAL POLICY BOUNDARIES
-- ============================================================

\echo ''
\echo '5. HISTORICAL MEDICAL POLICY RECORDS'

SELECT
    m.source_program_code,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    m.resolved_accounting_disposition,
    m.methodology_version,
    s.preferred_source,
    s.allocation_source,
    s.ledger_treatment,
    s.methodology_version AS source_policy_version
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.methodology_version = 'ANALYSIS-211M-v1'
ORDER BY m.source_program_code;

-- ============================================================
-- 6. INSPECT AL 64.029 EXISTING POLICY COVERAGE
-- ============================================================

\echo ''
\echo '6. AL 64.029 EXISTING POLICY COVERAGE'

SELECT
    m.source_program_code,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    m.resolved_accounting_disposition,
    m.methodology_version,
    s.preferred_source,
    s.allocation_source,
    s.ledger_treatment
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code = '64.029'
ORDER BY
    m.valid_from_fiscal_year,
    m.methodology_version;

ROLLBACK;

\echo ''
\echo 'ETL-211N1 COMPLETE - NO DATABASE WRITES'
