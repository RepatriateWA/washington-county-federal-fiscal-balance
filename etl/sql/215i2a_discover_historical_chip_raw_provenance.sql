
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-215I2A - HISTORICAL CHIP RAW PROVENANCE DISCOVERY'
\echo 'FY2018-FY2019 / READ ONLY / NO POLICY CHANGES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. HISTORICAL RESIDUAL BASELINE'

DO $check$
DECLARE
    v_count bigint;
    v_amount numeric;
BEGIN
    SELECT
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0)
    INTO v_count, v_amount
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
      AND BTRIM(cfda_number) = '93.767'
      AND award_id_fain IN (
          '1805WA5R21',
          '1Z0CMS330855',
          '0905WACPBP',
          '1005WACPBP',
          '1105WACPBP',
          '1205WACPBP'
      );

    IF v_count <> 11 OR v_amount <> -19561782.00 THEN
        RAISE EXCEPTION
            'BLOCK: residual population changed: % rows / %',
            v_count, v_amount;
    END IF;

    RAISE NOTICE
        'ETL-215I2A BASELINE PASS: 11 transactions / -$19561782';
END
$check$;

\echo ''
\echo '2. RAW AND STAGING RELATION INVENTORY'

SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    CASE c.relkind
        WHEN 'r' THEN 'TABLE'
        WHEN 'p' THEN 'PARTITIONED TABLE'
        WHEN 'v' THEN 'VIEW'
        WHEN 'm' THEN 'MATERIALIZED VIEW'
        ELSE c.relkind::text
    END AS relation_type,
    obj_description(c.oid, 'pg_class') AS description
FROM pg_class c
JOIN pg_namespace n
  ON n.oid = c.relnamespace
WHERE n.nspname NOT IN (
    'pg_catalog', 'information_schema'
)
  AND c.relkind IN ('r', 'p', 'v', 'm')
  AND (
      c.relname ILIKE '%assistance%'
      OR c.relname ILIKE '%award%transaction%'
      OR c.relname ILIKE '%observation%'
      OR c.relname ILIKE '%load%batch%'
  )
ORDER BY n.nspname, c.relname;

\echo ''
\echo '3. CANDIDATE RAW-SOURCE COLUMN INVENTORY'

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema NOT IN (
    'pg_catalog', 'information_schema'
)
  AND (
      table_name ILIKE '%assistance%'
      OR table_name ILIKE '%award%transaction%'
      OR table_name ILIKE '%observation%'
  )
  AND (
      column_name ILIKE '%description%'
      OR column_name ILIKE '%award%'
      OR column_name ILIKE '%transaction%'
      OR column_name ILIKE '%recipient%'
      OR column_name ILIKE '%agency%'
      OR column_name ILIKE '%account%'
      OR column_name ILIKE '%modif%'
      OR column_name ILIKE '%action%'
      OR column_name ILIKE '%source%'
      OR column_name ILIKE '%raw%'
      OR column_name ILIKE '%batch%'
      OR column_name ILIKE '%uri%'
      OR column_name ILIKE '%fain%'
      OR column_name ILIKE '%cfda%'
      OR column_name ILIKE '%federal%'
      OR column_name ILIKE '%json%'
      OR column_name ILIKE '%payload%'
  )
ORDER BY table_schema, table_name, ordinal_position;

\echo ''
\echo '4. VERIFIED OBSERVATION-LINKAGE INVENTORY'

SELECT
    a.action_date_fiscal_year AS fy,
    a.assistance_transaction_id,
    a.award_id_fain,
    a.federal_action_obligation,
    o.raw_assistance_transaction_id,
    o.award_transaction_observation_id,
    o.recipient_id,
    o.recipient_identity_key,
    o.funding_agency_id,
    o.awarding_agency_id
FROM analysis.v_certified_assistance_ledger a
LEFT JOIN analysis.v_assistance_transaction_observation_ledger o
  ON o.assistance_transaction_id =
     a.assistance_transaction_id
WHERE (
    (a.load_batch_id = 20 AND a.action_date_fiscal_year = 2018)
    OR
    (a.load_batch_id = 21 AND a.action_date_fiscal_year = 2019)
)
  AND BTRIM(a.cfda_number) = '93.767'
  AND a.award_id_fain IN (
      '1805WA5R21',
      '1Z0CMS330855',
      '0905WACPBP',
      '1005WACPBP',
      '1105WACPBP',
      '1205WACPBP'
  )
ORDER BY
    a.award_id_fain,
    a.action_date,
    a.assistance_transaction_id;

\echo ''
\echo '5. FOREIGN-KEY RELATIONSHIPS FOR RAW TABLES'

SELECT
    con.conrelid::regclass AS source_relation,
    con.conname AS constraint_name,
    con.confrelid::regclass AS referenced_relation,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint con
WHERE con.contype = 'f'
  AND (
      con.conrelid::regclass::text ILIKE '%assistance%'
      OR con.conrelid::regclass::text ILIKE '%observation%'
      OR con.confrelid::regclass::text ILIKE '%assistance%'
      OR con.confrelid::regclass::text ILIKE '%observation%'
  )
ORDER BY 1, 2;

ROLLBACK;

\echo ''
\echo 'ETL-215I2A COMPLETE - READ ONLY'
