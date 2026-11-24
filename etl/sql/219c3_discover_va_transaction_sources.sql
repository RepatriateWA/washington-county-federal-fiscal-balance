
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-219C3 - VA TRANSACTION SOURCE DISCOVERY'
\echo 'READ ONLY / NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';
SET LOCAL lock_timeout = '15s';

\echo ''
\echo '1. ALL PROCUREMENT / CONTRACT / TRANSACTION RELATIONS'

SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    CASE c.relkind
        WHEN 'r' THEN 'TABLE'
        WHEN 'p' THEN 'PARTITIONED TABLE'
        WHEN 'v' THEN 'VIEW'
        WHEN 'm' THEN 'MATERIALIZED VIEW'
        ELSE c.relkind::text
    END AS relation_type
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','p','v','m')
  AND n.nspname NOT IN (
      'pg_catalog','information_schema'
  )
  AND n.nspname NOT LIKE 'pg_toast%'
  AND (
      n.nspname ILIKE '%proc%'
      OR n.nspname ILIKE '%usaspending%'
      OR c.relname ILIKE '%procurement%'
      OR c.relname ILIKE '%contract%'
      OR c.relname ILIKE '%transaction%'
      OR c.relname ILIKE '%obligation%'
  )
ORDER BY n.nspname,c.relname;

\echo ''
\echo '2. PROCUREMENT-RELEVANT COLUMN INVENTORY'

SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    a.attnum AS ordinal_position,
    a.attname AS column_name,
    format_type(a.atttypid,a.atttypmod) AS column_type
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid
WHERE c.relkind IN ('r','p','v','m')
  AND a.attnum > 0
  AND NOT a.attisdropped
  AND n.nspname NOT IN (
      'pg_catalog','information_schema'
  )
  AND (
      n.nspname ILIKE '%proc%'
      OR c.relname ILIKE '%procurement%'
      OR c.relname ILIKE '%contract%'
  )
  AND (
      a.attname ILIKE '%agency%'
      OR a.attname ILIKE '%fiscal%'
      OR a.attname ILIKE '%obligation%'
      OR a.attname ILIKE '%outlay%'
      OR a.attname ILIKE '%amount%'
      OR a.attname ILIKE '%award%'
      OR a.attname ILIKE '%place%'
      OR a.attname ILIKE '%state%'
      OR a.attname ILIKE '%date%'
      OR a.attname ILIKE '%batch%'
  )
ORDER BY n.nspname,c.relname,a.attnum;

\echo ''
\echo '3. ASSISTANCE LEDGER CLASSIFICATION-RELEVANT COLUMNS'

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'analysis'
  AND table_name = 'v_certified_assistance_ledger'
  AND (
      column_name ILIKE '%cfda%'
      OR column_name ILIKE '%listing%'
      OR column_name ILIKE '%agency%'
      OR column_name ILIKE '%award%'
      OR column_name ILIKE '%fiscal%'
      OR column_name ILIKE '%obligation%'
      OR column_name ILIKE '%transaction%'
  )
ORDER BY ordinal_position;

\echo ''
\echo '4. EXISTING CLASSIFICATION RESOLUTION OBJECTS'

SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','p','v','m')
  AND (
      c.relname ILIKE '%classification%'
      OR c.relname ILIKE '%disposition%'
      OR c.relname ILIKE '%policy%'
      OR c.relname ILIKE '%overlap%'
  )
  AND n.nspname NOT IN (
      'pg_catalog','information_schema'
  )
ORDER BY n.nspname,c.relname;

\echo ''
\echo '5. CLASSIFICATION SOURCE-SYSTEM INVENTORY'

SELECT
    source_system,
    inflow_family,
    accounting_disposition,
    COUNT(*) AS classification_rows
FROM reference.federal_inflow_award_classification
GROUP BY
    source_system,
    inflow_family,
    accounting_disposition
ORDER BY
    source_system,
    inflow_family,
    accounting_disposition;

\echo ''
\echo '6. READ-ONLY EXECUTION GATE'

DO $gate$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION
            'BLOCK: transaction not read-only';
    END IF;

    IF to_regclass(
        'reference.federal_inflow_program_policy_mapping'
    ) IS NULL
       OR to_regclass(
        'analysis.v_certified_assistance_ledger'
    ) IS NULL
    THEN
        RAISE EXCEPTION
            'BLOCK: required assistance evidence objects absent';
    END IF;

    RAISE NOTICE
        'ETL-219C3 PASS: schema discovery completed; no overlap authorization granted';
END
$gate$;

ROLLBACK;

\echo ''
\echo 'ETL-219C3 COMPLETE - READ ONLY'
