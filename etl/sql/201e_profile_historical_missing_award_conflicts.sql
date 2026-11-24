
\set ON_ERROR_STOP on

BEGIN;
SET TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '120s';

\echo ''
\echo '============================================================'
\echo 'WCFFBP - ETL-201E'
\echo 'TARGETED HISTORICAL MISSING-AWARD CONFLICT PROFILE'
\echo 'FY2018 batch 20 / FY2019 batch 21'
\echo 'READ ONLY'
\echo '============================================================'

WITH historical AS MATERIALIZED (
    SELECT
        assistance_award_unique_key AS award_key,
        load_batch_id,
        source_row_number,
        NULLIF(
            BTRIM(raw_record ->> 'cfda_number'), ''
        ) AS listing_code,
        NULLIF(
            BTRIM(raw_record ->> 'assistance_type_code'), ''
        ) AS type_code,
        LEFT(
            BTRIM(raw_record ->> 'action_date'), 10
        ) AS action_date_text
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
),
conflicted AS MATERIALIZED (
    SELECT award_key
    FROM historical
    GROUP BY award_key
    HAVING COUNT(DISTINCT listing_code) > 1
        OR COUNT(DISTINCT type_code) > 1
)
SELECT
    COUNT(*) AS conflicted_historical_awards,
    COUNT(*) FILTER (
        WHERE a.assistance_award_id IS NULL
    ) AS conflicted_missing_awards,
    COUNT(*) FILTER (
        WHERE a.assistance_award_id IS NOT NULL
    ) AS conflicted_existing_awards
FROM conflicted AS c
LEFT JOIN assistance.award AS a
  ON a.assistance_award_unique_key = c.award_key;

ROLLBACK;
