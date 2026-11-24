
\set ON_ERROR_STOP on

BEGIN;
SET TRANSACTION READ ONLY;

-- Prevent another unexpectedly long execution.
SET LOCAL statement_timeout = '120s';

\echo ''
\echo '============================================================'
\echo 'WCFFBP - ETL-201B v0.2'
\echo 'HISTORICAL ASSISTANCE SOURCE CLASSIFICATION PROFILE'
\echo 'FY2018 batch 20 / FY2019 batch 21'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

\echo ''
\echo 'SECTION 1 - HISTORICAL SOURCE CONFLICTS'
\echo ''

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
profile AS (
    SELECT
        award_key,
        COUNT(*) AS observation_count,
        COUNT(DISTINCT listing_code)
            AS listing_variants,
        COUNT(DISTINCT type_code)
            AS type_variants,
        COUNT(DISTINCT load_batch_id)
            AS batch_count
    FROM historical
    GROUP BY award_key
)
SELECT
    COUNT(*) AS historical_source_awards,
    COUNT(*) FILTER (
        WHERE listing_variants > 1
    ) AS listing_conflicts,
    COUNT(*) FILTER (
        WHERE type_variants > 1
    ) AS type_conflicts,
    COUNT(*) FILTER (
        WHERE listing_variants > 1
           OR type_variants > 1
    ) AS any_classification_conflict,
    COUNT(*) FILTER (
        WHERE listing_variants > 1
          AND type_variants > 1
    ) AS both_conflict_types,
    COUNT(*) FILTER (
        WHERE (
            listing_variants > 1
            OR type_variants > 1
        )
        AND batch_count = 2
    ) AS crossyear_conflicts
FROM profile;

\echo ''
\echo 'SECTION 2 - EXISTING AWARD COVERAGE'
\echo ''

WITH historical_keys AS MATERIALIZED (
    SELECT DISTINCT
        assistance_award_unique_key AS award_key
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
)
SELECT
    COUNT(*) AS historical_awards,
    COUNT(*) FILTER (
        WHERE a.assistance_award_id IS NOT NULL
    ) AS existing_canonical_awards,
    COUNT(*) FILTER (
        WHERE a.assistance_award_id IS NULL
    ) AS missing_canonical_awards
FROM historical_keys AS h
LEFT JOIN assistance.award AS a
  ON a.assistance_award_unique_key = h.award_key;

ROLLBACK;
