
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '======================================================'
\echo 'ETL-213T v0.1 - VA IMAGING LOCATION RELATIONSHIP'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '======================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. Imaging recipient versus performance geography'

WITH imaging AS (
    SELECT
        t.fiscal_year,
        t.federal_action_obligation AS obligation,
        r.raw_record->>'recipient_name'
            AS recipient_name,
        r.raw_record->>'recipient_uei'
            AS recipient_uei,
        r.raw_record->>'recipient_city_name'
            AS recipient_city,
        r.raw_record->>'recipient_county_name'
            AS recipient_county,
        r.raw_record->>'recipient_state_name'
            AS recipient_state,
        r.raw_record->>'primary_place_of_performance_city_name'
            AS performance_city,
        r.raw_record->>'primary_place_of_performance_county_name'
            AS performance_county,
        r.raw_record->>'primary_place_of_performance_state_name'
            AS performance_state
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id = r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id = o.award_transaction_id
    WHERE r.load_batch_id IN (22, 23)
      AND BTRIM(r.raw_record->>'funding_agency_code') = '036'
      AND t.psc_code = '6525'
)
SELECT
    recipient_name,
    recipient_uei,
    recipient_city,
    recipient_county,
    recipient_state,
    performance_city,
    performance_county,
    performance_state,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation), 2) AS net_obligations,
    ROUND(SUM(ABS(obligation)), 2)
        AS gross_absolute_obligations
FROM imaging
GROUP BY
    recipient_name,
    recipient_uei,
    recipient_city,
    recipient_county,
    recipient_state,
    performance_city,
    performance_county,
    performance_state
ORDER BY gross_absolute_obligations DESC
LIMIT 25;

\echo ''
\echo '2. Philips location pattern by fiscal year'

SELECT
    t.fiscal_year,
    r.raw_record->>'recipient_city_name'
        AS recipient_city,
    r.raw_record->>'recipient_county_name'
        AS recipient_county,
    r.raw_record->>'recipient_state_name'
        AS recipient_state,
    r.raw_record->>'primary_place_of_performance_city_name'
        AS performance_city,
    r.raw_record->>'primary_place_of_performance_county_name'
        AS performance_county,
    COUNT(*) AS transactions,
    ROUND(SUM(t.federal_action_obligation), 2)
        AS net_obligations
FROM procurement.raw_award_transaction r
JOIN procurement.award_transaction_observation o
  ON o.raw_award_transaction_id = r.raw_award_transaction_id
JOIN procurement.award_transaction t
  ON t.award_transaction_id = o.award_transaction_id
WHERE r.load_batch_id IN (22, 23)
  AND BTRIM(r.raw_record->>'funding_agency_code') = '036'
  AND t.psc_code = '6525'
  AND r.raw_record->>'recipient_uei' = 'L39CAPDUSB98'
GROUP BY
    t.fiscal_year,
    r.raw_record->>'recipient_city_name',
    r.raw_record->>'recipient_county_name',
    r.raw_record->>'recipient_state_name',
    r.raw_record->>'primary_place_of_performance_city_name',
    r.raw_record->>'primary_place_of_performance_county_name'
ORDER BY t.fiscal_year, ABS(SUM(t.federal_action_obligation)) DESC;

\echo ''
\echo '3. Six named out-of-state destinations: location fields'

SELECT
    t.award_transaction_id,
    a.piid,
    r.raw_record->>'recipient_name'
        AS recipient_name,
    r.raw_record->>'recipient_city_name'
        AS recipient_city,
    r.raw_record->>'recipient_county_name'
        AS recipient_county,
    r.raw_record->>'recipient_state_name'
        AS recipient_state,
    r.raw_record->>'recipient_address_line_1'
        AS recipient_address,
    r.raw_record->>'primary_place_of_performance_city_name'
        AS performance_city,
    r.raw_record->>'primary_place_of_performance_county_name'
        AS performance_county,
    LEFT(t.transaction_description, 180)
        AS destination_description
FROM procurement.raw_award_transaction r
JOIN procurement.award_transaction_observation o
  ON o.raw_award_transaction_id = r.raw_award_transaction_id
JOIN procurement.award_transaction t
  ON t.award_transaction_id = o.award_transaction_id
JOIN procurement.award a
  ON a.award_id = t.award_id
WHERE r.load_batch_id IN (22, 23)
  AND t.award_transaction_id IN (
      839931, 824816, 824523,
      818009, 808542, 820659
  )
ORDER BY t.award_transaction_id;

ROLLBACK;

\echo ''
\echo 'ETL-213T v0.1 COMPLETE - NO DATABASE WRITES'
