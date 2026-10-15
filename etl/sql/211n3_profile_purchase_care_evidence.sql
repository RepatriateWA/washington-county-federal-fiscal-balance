
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-211N3 - PURCHASE CARE HISTORICAL EVIDENCE'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. TRANSACTION ASSISTANCE TYPES'

SELECT
    c.action_date_fiscal_year AS fiscal_year,
    c.assistance_type_code,
    c.assistance_type_description,
    COUNT(*) AS transactions,
    ROUND(SUM(c.federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger c
WHERE BTRIM(c.cfda_number) = '64.029'
  AND (
      (c.load_batch_id = 20
       AND c.action_date_fiscal_year = 2018)
      OR
      (c.load_batch_id = 21
       AND c.action_date_fiscal_year = 2019)
  )
GROUP BY
    c.action_date_fiscal_year,
    c.assistance_type_code,
    c.assistance_type_description
ORDER BY fiscal_year, transactions DESC;

\echo ''
\echo '2. RECIPIENT PROFILE'

SELECT
    c.action_date_fiscal_year AS fiscal_year,
    c.recipient_name,
    COUNT(*) AS transactions,
    ROUND(SUM(c.federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger c
WHERE BTRIM(c.cfda_number) = '64.029'
  AND (
      (c.load_batch_id = 20
       AND c.action_date_fiscal_year = 2018)
      OR
      (c.load_batch_id = 21
       AND c.action_date_fiscal_year = 2019)
  )
GROUP BY
    c.action_date_fiscal_year,
    c.recipient_name
ORDER BY fiscal_year, net_obligations DESC
LIMIT 30;

\echo ''
\echo '3. TRANSACTION DESCRIPTION PROFILE'

SELECT
    c.action_date_fiscal_year AS fiscal_year,
    LEFT(
        COALESCE(c.transaction_description, '[NULL]'),
        160
    ) AS description,
    COUNT(*) AS transactions,
    ROUND(SUM(c.federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger c
WHERE BTRIM(c.cfda_number) = '64.029'
  AND (
      (c.load_batch_id = 20
       AND c.action_date_fiscal_year = 2018)
      OR
      (c.load_batch_id = 21
       AND c.action_date_fiscal_year = 2019)
  )
GROUP BY
    c.action_date_fiscal_year,
    LEFT(
        COALESCE(c.transaction_description, '[NULL]'),
        160
    )
ORDER BY fiscal_year, net_obligations DESC
LIMIT 40;

\echo ''
\echo '4. GDX SOURCE SCHEMA INVENTORY'

SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'va'
  AND (
      table_name ILIKE '%gdx%'
      OR column_name ILIKE '%source%'
      OR column_name ILIKE '%vintage%'
      OR column_name ILIKE '%methodology%'
  )
ORDER BY table_name, ordinal_position;

ROLLBACK;

\echo ''
\echo 'ETL-211N3 COMPLETE - NO DATABASE WRITES'
