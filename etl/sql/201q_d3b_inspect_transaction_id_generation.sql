
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-201Q STAGE D.3B - TRANSACTION ID GENERATION'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;

\echo ''
\echo 'SECTION 1 - PRIMARY KEY GENERATION METADATA'

SELECT
    a.attname AS column_name,
    a.attidentity AS identity_type,
    a.attgenerated AS generated_type,
    pg_get_expr(d.adbin, d.adrelid) AS default_expression
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_attrdef d
  ON d.adrelid = a.attrelid
 AND d.adnum = a.attnum
WHERE n.nspname = 'assistance'
  AND c.relname IN (
      'award_transaction',
      'award_transaction_observation'
  )
  AND a.attname IN (
      'assistance_transaction_id',
      'award_transaction_observation_id'
  )
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY c.relname, a.attname;

\echo ''
\echo 'SECTION 2 - INSERT TRIGGERS'

SELECT
    c.relname AS table_name,
    t.tgname AS trigger_name,
    pg_get_triggerdef(t.oid) AS trigger_definition
FROM pg_trigger t
JOIN pg_class c ON c.oid = t.tgrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'assistance'
  AND c.relname IN (
      'award_transaction',
      'award_transaction_observation'
  )
  AND NOT t.tgisinternal
ORDER BY c.relname, t.tgname;

\echo ''
\echo 'SECTION 3 - ASSOCIATED SEQUENCES'

SELECT
    c.relname AS table_name,
    a.attname AS column_name,
    pg_get_serial_sequence(
        format('%I.%I', n.nspname, c.relname),
        a.attname
    ) AS associated_sequence
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid
WHERE n.nspname = 'assistance'
  AND c.relname IN (
      'award_transaction',
      'award_transaction_observation'
  )
  AND a.attname IN (
      'assistance_transaction_id',
      'award_transaction_observation_id'
  )
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY c.relname, a.attname;

ROLLBACK;

\echo ''
\echo 'ETL-201Q STAGE D.3B COMPLETE - READ ONLY'
