
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '======================================================'
\echo 'ETL-213S v0.1 - VA IMAGING SUPPLIER PROFILE'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '======================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. Supplier identity field inventory'

WITH sample AS (
    SELECT raw_record
    FROM procurement.raw_award_transaction
    WHERE load_batch_id IN (22, 23)
      AND BTRIM(raw_record->>'funding_agency_code') = '036'
      AND BTRIM(
          raw_record->>'product_or_service_code'
      ) = '6525'
    LIMIT 100
)
SELECT
    k.key,
    COUNT(*) AS occurrences,
    COUNT(*) FILTER (
        WHERE NULLIF(BTRIM(s.raw_record->>k.key), '')
              IS NOT NULL
    ) AS populated
FROM sample s
CROSS JOIN LATERAL
    JSONB_OBJECT_KEYS(s.raw_record) AS k(key)
WHERE k.key ~* 'recipient|vendor|place_of_performance'
GROUP BY k.key
ORDER BY k.key;

\echo ''
\echo '2. Top raw recipient identities in PSC 6525'

SELECT
    t.fiscal_year,
    r.raw_record->>'recipient_name'
        AS recipient_name,
    r.raw_record->>'recipient_uei'
        AS recipient_uei,
    COUNT(*) AS transactions,
    ROUND(SUM(t.federal_action_obligation), 2)
        AS net_obligations,
    ROUND(SUM(ABS(t.federal_action_obligation)), 2)
        AS gross_absolute_obligations
FROM procurement.raw_award_transaction r
JOIN procurement.award_transaction_observation o
  ON o.raw_award_transaction_id = r.raw_award_transaction_id
JOIN procurement.award_transaction t
  ON t.award_transaction_id = o.award_transaction_id
WHERE r.load_batch_id IN (22, 23)
  AND BTRIM(r.raw_record->>'funding_agency_code') = '036'
  AND t.psc_code = '6525'
GROUP BY
    t.fiscal_year,
    r.raw_record->>'recipient_name',
    r.raw_record->>'recipient_uei'
ORDER BY gross_absolute_obligations DESC
LIMIT 25;

\echo ''
\echo '3. Original geography fields for named destinations'

SELECT
    t.fiscal_year,
    t.award_transaction_id,
    a.piid,
    ROUND(t.federal_action_obligation, 2)
        AS obligation,
    r.raw_record->>'recipient_name'
        AS recipient_name,
    r.raw_record->>'primary_place_of_performance_county_name'
        AS raw_performance_county,
    r.raw_record->>'primary_place_of_performance_state_name'
        AS raw_performance_state,
    r.raw_record->>'recipient_location_county_name'
        AS raw_recipient_county,
    r.raw_record->>'recipient_location_state_name'
        AS raw_recipient_state,
    LEFT(t.transaction_description, 250)
        AS description
FROM procurement.raw_award_transaction r
JOIN procurement.award_transaction_observation o
  ON o.raw_award_transaction_id = r.raw_award_transaction_id
JOIN procurement.award_transaction t
  ON t.award_transaction_id = o.award_transaction_id
JOIN procurement.award a
  ON a.award_id = t.award_id
WHERE r.load_batch_id IN (22, 23)
  AND BTRIM(r.raw_record->>'funding_agency_code') = '036'
  AND t.award_transaction_id IN (
      839931,
      824816,
      824523,
      818009,
      808542,
      820659
  )
ORDER BY ABS(t.federal_action_obligation) DESC;

ROLLBACK;

\echo ''
\echo 'ETL-213S v0.1 COMPLETE - NO DATABASE WRITES'
