
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '======================================================'
\echo 'ETL-213U v0.1 - VA BOTHELL PERFORMANCE AUDIT'
\echo 'FY2018-FY2019 - READ ONLY'
\echo '======================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. Philips Bothell performance ZIP distribution'

WITH philips AS (
    SELECT
        t.fiscal_year,
        t.federal_action_obligation AS obligation,
        r.raw_record->>'primary_place_of_performance_zip_4'
            AS performance_zip,
        r.raw_record->>'primary_place_of_performance_city_name'
            AS performance_city,
        r.raw_record->>'primary_place_of_performance_county_name'
            AS performance_county,
        r.raw_record->>'primary_place_of_performance_state_code'
            AS performance_state
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id = r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id = o.award_transaction_id
    WHERE r.load_batch_id IN (22, 23)
      AND BTRIM(r.raw_record->>'funding_agency_code') = '036'
      AND t.psc_code = '6525'
      AND r.raw_record->>'recipient_uei' = 'L39CAPDUSB98'
      AND UPPER(BTRIM(
          r.raw_record->>'primary_place_of_performance_city_name'
      )) = 'BOTHELL'
      AND UPPER(BTRIM(
          r.raw_record->>'primary_place_of_performance_county_name'
      )) = 'SNOHOMISH'
)
SELECT
    fiscal_year,
    performance_zip,
    performance_city,
    performance_county,
    performance_state,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation), 2) AS net_obligations,
    ROUND(SUM(ABS(obligation)), 2)
        AS gross_absolute_obligations
FROM philips
GROUP BY
    fiscal_year,
    performance_zip,
    performance_city,
    performance_county,
    performance_state
ORDER BY fiscal_year, gross_absolute_obligations DESC;

\echo ''
\echo '2. Destination language in Philips Bothell contracts'

WITH philips AS (
    SELECT
        t.fiscal_year,
        t.federal_action_obligation AS obligation,
        COALESCE(t.transaction_description, '') || ' ' ||
        COALESCE(a.award_description, '') AS evidence_text
    FROM procurement.raw_award_transaction r
    JOIN procurement.award_transaction_observation o
      ON o.raw_award_transaction_id = r.raw_award_transaction_id
    JOIN procurement.award_transaction t
      ON t.award_transaction_id = o.award_transaction_id
    JOIN procurement.award a
      ON a.award_id = t.award_id
    WHERE r.load_batch_id IN (22, 23)
      AND BTRIM(r.raw_record->>'funding_agency_code') = '036'
      AND t.psc_code = '6525'
      AND r.raw_record->>'recipient_uei' = 'L39CAPDUSB98'
      AND UPPER(BTRIM(
          r.raw_record->>'primary_place_of_performance_city_name'
      )) = 'BOTHELL'
      AND UPPER(BTRIM(
          r.raw_record->>'primary_place_of_performance_county_name'
      )) = 'SNOHOMISH'
),
flags AS (
    SELECT
        *,
        evidence_text ~* (
            'VAMC|VA MEDICAL CENTER|VA HOSPITAL|' ||
            'VETERANS AFFAIRS MEDICAL CENTER'
        ) AS named_facility_language,
        evidence_text ~* (
            'BALTIMORE|HOUSTON|KANSAS CITY|' ||
            'ST LOUIS|ST[.] LOUIS|LAKE CITY, FL|' ||
            'OVERTON BROOKS|CHICAGO|MARYLAND|' ||
            'FLORIDA|TEXAS|LOUISIANA'
        ) AS selected_out_of_state_language
    FROM philips
)
SELECT
    fiscal_year,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation), 2) AS total_net,
    COUNT(*) FILTER (WHERE named_facility_language)
        AS facility_language_count,
    ROUND(COALESCE(SUM(obligation) FILTER (
        WHERE named_facility_language
    ), 0), 2) AS facility_language_net,
    COUNT(*) FILTER (WHERE selected_out_of_state_language)
        AS selected_out_of_state_count,
    ROUND(COALESCE(SUM(obligation) FILTER (
        WHERE selected_out_of_state_language
    ), 0), 2) AS selected_out_of_state_net
FROM flags
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '3. Largest descriptions with selected destination language'

SELECT
    t.fiscal_year,
    t.award_transaction_id,
    a.piid,
    ROUND(t.federal_action_obligation, 2) AS obligation,
    LEFT(t.transaction_description, 350) AS description
FROM procurement.raw_award_transaction r
JOIN procurement.award_transaction_observation o
  ON o.raw_award_transaction_id = r.raw_award_transaction_id
JOIN procurement.award_transaction t
  ON t.award_transaction_id = o.award_transaction_id
JOIN procurement.award a
  ON a.award_id = t.award_id
WHERE r.load_batch_id IN (22, 23)
  AND BTRIM(r.raw_record->>'funding_agency_code') = '036'
  AND t.psc_code = '6525'
  AND r.raw_record->>'recipient_uei' = 'L39CAPDUSB98'
  AND UPPER(BTRIM(
      r.raw_record->>'primary_place_of_performance_city_name'
  )) = 'BOTHELL'
  AND UPPER(BTRIM(
      r.raw_record->>'primary_place_of_performance_county_name'
  )) = 'SNOHOMISH'
  AND (
      COALESCE(t.transaction_description, '') || ' ' ||
      COALESCE(a.award_description, '')
  ) ~* (
      'BALTIMORE|HOUSTON|KANSAS CITY|' ||
      'ST LOUIS|ST[.] LOUIS|LAKE CITY, FL|' ||
      'OVERTON BROOKS|CHICAGO|MARYLAND|' ||
      'FLORIDA|TEXAS|LOUISIANA'
  )
ORDER BY ABS(t.federal_action_obligation) DESC
LIMIT 30;

ROLLBACK;

\echo ''
\echo 'ETL-213U v0.1 COMPLETE - NO DATABASE WRITES'
