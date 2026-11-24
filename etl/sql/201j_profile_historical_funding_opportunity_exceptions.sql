
\set ON_ERROR_STOP on

BEGIN;
SET TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '300s';

\echo ''
\echo '============================================================'
\echo 'ETL-201J v0.1'
\echo 'HISTORICAL FUNDING-OPPORTUNITY EXCEPTION PROFILE'
\echo 'FY2018 batch 20 / FY2019 batch 21'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

-- Identify the exact 156,401-award candidate cohort.
-- Keep all observations for eligible award keys.

\echo ''
\echo 'SECTION 1 - MISSING OPPORTUNITY CODES AND THEIR SCOPE'

WITH historical AS MATERIALIZED (
    SELECT
        raw.assistance_award_unique_key AS award_key,
        raw.load_batch_id,
        raw.source_row_number,
        NULLIF(
            BTRIM(raw.raw_record ->> 'cfda_number'), ''
        ) AS listing_code,
        NULLIF(
            BTRIM(raw.raw_record ->> 'assistance_type_code'), ''
        ) AS type_code,
        NULLIF(
            BTRIM(
                raw.raw_record ->> 'funding_opportunity_number'
            ), ''
        ) AS opportunity_code,
        raw.raw_record ->> 'action_date' AS action_date_text
    FROM assistance.raw_award_transaction AS raw
    WHERE raw.load_batch_id IN (20, 21)
),
eligible AS MATERIALIZED (
    SELECT h.award_key
    FROM historical AS h
    LEFT JOIN assistance.award AS a
      ON a.assistance_award_unique_key = h.award_key
    WHERE a.assistance_award_unique_key IS NULL
    GROUP BY h.award_key
    HAVING COUNT(DISTINCT h.listing_code) <= 1
       AND COUNT(DISTINCT h.type_code) <= 1
),
missing AS (
    SELECT h.*
    FROM historical AS h
    JOIN eligible AS e ON e.award_key = h.award_key
    LEFT JOIN assistance.funding_opportunity AS f
      ON f.funding_opportunity_number = h.opportunity_code
    WHERE h.opportunity_code IS NOT NULL
      AND f.funding_opportunity_id IS NULL
)
SELECT
    opportunity_code,
    COUNT(*) AS source_observations,
    COUNT(DISTINCT award_key) AS distinct_awards,
    COUNT(*) FILTER (
        WHERE load_batch_id = 20
    ) AS fy2018_observations,
    COUNT(*) FILTER (
        WHERE load_batch_id = 21
    ) AS fy2019_observations,
    MIN(action_date_text) AS earliest_action_text,
    MAX(action_date_text) AS latest_action_text
FROM missing
GROUP BY opportunity_code
ORDER BY distinct_awards DESC, opportunity_code;

\echo ''
\echo 'SECTION 2 - POSSIBLE FORMATTING EQUIVALENTS'

WITH historical_codes AS MATERIALIZED (
    SELECT DISTINCT
        NULLIF(
            BTRIM(
                raw_record ->> 'funding_opportunity_number'
            ), ''
        ) AS opportunity_code
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
),
unresolved AS (
    SELECT h.opportunity_code
    FROM historical_codes AS h
    LEFT JOIN assistance.funding_opportunity AS f
      ON f.funding_opportunity_number = h.opportunity_code
    WHERE h.opportunity_code IS NOT NULL
      AND f.funding_opportunity_id IS NULL
)
SELECT
    u.opportunity_code AS source_code,
    f.funding_opportunity_number AS possible_match,
    f.funding_opportunity_id
FROM unresolved AS u
JOIN assistance.funding_opportunity AS f
  ON UPPER(
       REGEXP_REPLACE(u.opportunity_code, '[^A-Za-z0-9]', '', 'g')
     ) =
     UPPER(
       REGEXP_REPLACE(
           f.funding_opportunity_number,
           '[^A-Za-z0-9]', '', 'g'
       )
     )
ORDER BY u.opportunity_code, f.funding_opportunity_number;

ROLLBACK;

\echo ''
\echo 'ETL-201J COMPLETE - NO DATABASE WRITES'
