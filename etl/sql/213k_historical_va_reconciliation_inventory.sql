
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '======================================================'
\echo 'ETL-213K v0.1 - VA RECONCILIATION EVIDENCE INVENTORY'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '======================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '120s';

\echo ''
\echo '1. PSC and county reference schemas'

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE
    (table_schema = 'procurement'
     AND table_name IN ('psc', 'place'))
    OR
    (table_schema = 'reference'
     AND table_name = 'county_registry')
ORDER BY table_schema, table_name, ordinal_position;

\echo ''
\echo '2. Top VA-funded PSC codes: reference descriptions'

WITH va_psc AS (
    SELECT
        t.psc_code,
        COUNT(*) AS transactions,
        SUM(t.federal_action_obligation) AS net_obligations
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id =
         r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id =
         o.award_transaction_id
    WHERE r.load_batch_id IN (22, 23)
      AND BTRIM(
          r.raw_record->>'funding_agency_code'
      ) = '036'
    GROUP BY t.psc_code
)
SELECT
    v.psc_code,
    v.transactions,
    ROUND(v.net_obligations, 2) AS net_obligations,
    TO_JSONB(p) AS psc_reference_record
FROM va_psc v
LEFT JOIN procurement.psc p
  ON p.psc_code = v.psc_code
ORDER BY v.net_obligations DESC
LIMIT 25;

\echo ''
\echo '3. Historical contract timing field names'

WITH sample AS (
    SELECT raw_record
    FROM procurement.raw_award_transaction
    WHERE load_batch_id IN (22, 23)
    ORDER BY raw_award_transaction_id
    LIMIT 200
)
SELECT
    k.key,
    COUNT(*) AS sample_occurrences
FROM sample s
CROSS JOIN LATERAL
    JSONB_OBJECT_KEYS(s.raw_record) AS k(key)
WHERE k.key ~* 'performance|period|date|completion'
GROUP BY k.key
ORDER BY k.key;

\echo ''
\echo '4. Largest individual VA-funded transactions'

SELECT
    t.fiscal_year,
    t.award_transaction_id,
    a.piid,
    t.action_date,
    t.psc_code,
    ROUND(t.federal_action_obligation, 2)
        AS net_action_obligation,
    a.period_of_performance_start,
    a.period_of_performance_end,
    LEFT(a.award_description, 120)
        AS award_description
FROM procurement.raw_award_transaction r
JOIN procurement.award_transaction_observation o
  ON o.raw_award_transaction_id =
     r.raw_award_transaction_id
JOIN procurement.award_transaction t
  ON t.award_transaction_id =
     o.award_transaction_id
JOIN procurement.award a
  ON a.award_id = t.award_id
WHERE r.load_batch_id IN (22, 23)
  AND BTRIM(
      r.raw_record->>'funding_agency_code'
  ) = '036'
ORDER BY ABS(t.federal_action_obligation) DESC
LIMIT 20;

ROLLBACK;

\echo ''
\echo 'ETL-213K v0.1 COMPLETE - NO DATABASE WRITES'
