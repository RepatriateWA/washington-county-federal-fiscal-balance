
\set ON_ERROR_STOP on
\pset pager off

BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;
SET LOCAL statement_timeout = '300s';

\echo ''
\echo '======================================================================'
\echo 'ETL-201L v0.1 - HISTORICAL FUNDING-OPPORTUNITY REGISTRATION PREVIEW'
\echo 'FY2018 batch 20 / FY2019 batch 21'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '======================================================================'

\echo ''
\echo 'SECTION 1 - BASELINE REFERENCE POPULATION'

SELECT
    COUNT(*) AS existing_reference_rows,
    COUNT(DISTINCT funding_opportunity_number)
        AS distinct_reference_numbers,
    COUNT(*) FILTER (
        WHERE funding_opportunity_goals_text IS NULL
    ) AS null_goals_text_count
FROM assistance.funding_opportunity;

\echo ''
\echo 'SECTION 2 - REGISTRATION CANDIDATES'

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
unresolved AS (
    SELECT h.*
    FROM historical AS h
    JOIN eligible AS e
      ON e.award_key = h.award_key
    WHERE h.opportunity_code IS NOT NULL
      AND NOT EXISTS (
          SELECT 1
          FROM assistance.funding_opportunity AS f
          WHERE f.funding_opportunity_number =
                h.opportunity_code
      )
)
SELECT
    opportunity_code AS proposed_reference_number,
    NULL::text AS proposed_goals_text,
    COUNT(*) AS source_observations,
    COUNT(DISTINCT award_key) AS distinct_awards,
    COUNT(*) FILTER (
        WHERE load_batch_id = 20
    ) AS fy2018_observations,
    COUNT(*) FILTER (
        WHERE load_batch_id = 21
    ) AS fy2019_observations,
    MIN(action_date_text) AS first_action_date_text,
    MAX(action_date_text) AS last_action_date_text
FROM unresolved
GROUP BY opportunity_code
ORDER BY opportunity_code;

\echo ''
\echo 'SECTION 3 - REGISTRATION CONTROL TOTALS'

WITH historical AS MATERIALIZED (
    SELECT
        assistance_award_unique_key AS award_key,
        load_batch_id,
        source_row_number,
        NULLIF(
            BTRIM(raw_record ->> 'cfda_number'), ''
        ) AS listing_code,
        NULLIF(
            BTRIM(
                raw_record ->> 'assistance_type_code'
            ), ''
        ) AS type_code,
        NULLIF(
            BTRIM(
                raw_record ->> 'funding_opportunity_number'
            ), ''
        ) AS opportunity_code
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
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
unresolved AS MATERIALIZED (
    SELECT h.*
    FROM historical AS h
    JOIN eligible AS e ON e.award_key = h.award_key
    WHERE h.opportunity_code IS NOT NULL
      AND NOT EXISTS (
          SELECT 1
          FROM assistance.funding_opportunity AS f
          WHERE f.funding_opportunity_number =
                h.opportunity_code
      )
)
SELECT
    COUNT(DISTINCT opportunity_code)
        AS proposed_reference_rows,
    COUNT(*) AS affected_source_observations,
    COUNT(DISTINCT award_key) AS affected_awards,
    COUNT(DISTINCT (
        load_batch_id,
        source_row_number
    )) AS distinct_source_identities,
    (
        SELECT COUNT(*)
        FROM assistance.funding_opportunity
    ) AS existing_reference_rows,
    (
        SELECT COUNT(*)
        FROM assistance.funding_opportunity
    ) + COUNT(DISTINCT opportunity_code)
        AS projected_reference_rows
FROM unresolved;

\echo ''
\echo 'SECTION 4 - SOURCE-LEVEL PROVENANCE'

WITH historical AS MATERIALIZED (
    SELECT
        raw.assistance_award_unique_key AS award_key,
        raw.load_batch_id,
        raw.source_row_number,
        NULLIF(
            BTRIM(raw.raw_record ->> 'cfda_number'), ''
        ) AS listing_code,
        NULLIF(
            BTRIM(
                raw.raw_record ->> 'assistance_type_code'
            ), ''
        ) AS type_code,
        NULLIF(
            BTRIM(
                raw.raw_record ->> 'funding_opportunity_number'
            ), ''
        ) AS opportunity_code,
        raw.raw_record ->> 'action_date'
            AS action_date_text,
        raw.raw_record ->> 'award_id_fain'
            AS award_id_fain,
        raw.raw_record ->> 'award_id_uri'
            AS award_id_uri
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
)
SELECT
    h.opportunity_code,
    h.award_key,
    h.load_batch_id,
    h.source_row_number,
    h.action_date_text,
    h.award_id_fain,
    h.award_id_uri
FROM historical AS h
JOIN eligible AS e ON e.award_key = h.award_key
WHERE h.opportunity_code IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM assistance.funding_opportunity AS f
      WHERE f.funding_opportunity_number =
            h.opportunity_code
  )
ORDER BY
    h.opportunity_code,
    h.award_key,
    h.load_batch_id,
    h.source_row_number;

ROLLBACK;

\echo ''
\echo 'ETL-201L STAGE A COMPLETE - NO DATABASE WRITES'
