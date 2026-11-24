
\set ON_ERROR_STOP on

BEGIN;
SET TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '120s';

\echo ''
\echo '============================================================'
\echo 'WCFFBP - ETL-201F v0.1'
\echo 'HISTORICAL MISSING-AWARD CLASSIFICATION EXCEPTIONS'
\echo 'FY2018 batch 20 / FY2019 batch 21'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

\echo ''
\echo 'SECTION 1 - EXCEPTION CLASSIFICATION PROFILE'
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
        NULLIF(
            BTRIM(raw_record ->> 'award_id_fain'), ''
        ) AS source_fain,
        NULLIF(
            BTRIM(raw_record ->> 'award_id_uri'), ''
        ) AS source_uri,
        LEFT(
            BTRIM(raw_record ->> 'action_date'), 10
        ) AS action_date_text
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
),
conflicted AS MATERIALIZED (
    SELECT
        award_key,
        COUNT(DISTINCT listing_code)
            AS listing_variants,
        COUNT(DISTINCT type_code)
            AS type_variants,
        COUNT(DISTINCT load_batch_id)
            AS batch_count
    FROM historical
    GROUP BY award_key
    HAVING COUNT(DISTINCT listing_code) > 1
        OR COUNT(DISTINCT type_code) > 1
),
missing_conflicted AS MATERIALIZED (
    SELECT c.*
    FROM conflicted AS c
    WHERE NOT EXISTS (
        SELECT 1
        FROM assistance.award AS a
        WHERE a.assistance_award_unique_key = c.award_key
    )
),
exception_rows AS MATERIALIZED (
    SELECT
        h.*,
        c.listing_variants,
        c.type_variants,
        c.batch_count,
        CASE
            WHEN h.action_date_text ~
                 '^\d{4}-\d{2}-\d{2}$'
            THEN h.action_date_text::date
            ELSE NULL
        END AS action_date
    FROM historical AS h
    JOIN missing_conflicted AS c
      ON c.award_key = h.award_key
),
dated AS (
    SELECT
        e.*,
        MAX(action_date) OVER (
            PARTITION BY award_key
        ) AS latest_action_date
    FROM exception_rows AS e
),
exception_profile AS (
    SELECT
        award_key,
        MAX(listing_variants) AS listing_variants,
        MAX(type_variants) AS type_variants,
        MAX(batch_count) AS batch_count,
        COUNT(*) AS observation_count,
        COUNT(DISTINCT action_date)
            AS distinct_action_dates,
        MIN(action_date) AS earliest_action_date,
        MAX(action_date) AS latest_action_date,
        COUNT(*) FILTER (
            WHERE action_date = latest_action_date
        ) AS latest_date_observations,
        COUNT(DISTINCT listing_code) FILTER (
            WHERE action_date = latest_action_date
        ) AS latest_listing_variants,
        COUNT(DISTINCT type_code) FILTER (
            WHERE action_date = latest_action_date
        ) AS latest_type_variants,
        COUNT(*) FILTER (
            WHERE action_date IS NULL
        ) AS missing_date_observations
    FROM dated
    GROUP BY award_key
)
SELECT
    COUNT(*) AS missing_conflicted_awards,

    COUNT(*) FILTER (
        WHERE listing_variants > 1
    ) AS listing_conflicts,

    COUNT(*) FILTER (
        WHERE type_variants > 1
    ) AS type_conflicts,

    COUNT(*) FILTER (
        WHERE listing_variants > 1
          AND type_variants > 1
    ) AS both_conflict_types,

    COUNT(*) FILTER (
        WHERE batch_count = 2
    ) AS crossyear_conflicts,

    COUNT(*) FILTER (
        WHERE distinct_action_dates > 1
    ) AS conflicts_with_multiple_dates,

    COUNT(*) FILTER (
        WHERE distinct_action_dates = 1
    ) AS conflicts_with_single_date,

    COUNT(*) FILTER (
        WHERE latest_date_observations > 1
    ) AS latest_date_ties,

    COUNT(*) FILTER (
        WHERE latest_listing_variants > 1
           OR latest_type_variants > 1
    ) AS latest_date_classification_conflicts,

    COUNT(*) FILTER (
        WHERE missing_date_observations > 0
    ) AS awards_with_missing_dates,

    COUNT(*) FILTER (
        WHERE latest_listing_variants = 1
          AND latest_type_variants = 1
          AND missing_date_observations = 0
    ) AS latest_date_consistent_candidates

FROM exception_profile;

\echo ''
\echo 'SECTION 2 - SELECTED OBSERVATION DETAILS'
\echo 'One latest observation per conflicting missing award'
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
        NULLIF(
            BTRIM(raw_record ->> 'award_id_fain'), ''
        ) AS source_fain,
        NULLIF(
            BTRIM(raw_record ->> 'award_id_uri'), ''
        ) AS source_uri,
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
),
missing_conflicted AS MATERIALIZED (
    SELECT c.award_key
    FROM conflicted AS c
    WHERE NOT EXISTS (
        SELECT 1
        FROM assistance.award AS a
        WHERE a.assistance_award_unique_key = c.award_key
    )
),
ranked AS (
    SELECT
        h.*,
        ROW_NUMBER() OVER (
            PARTITION BY h.award_key
            ORDER BY
                h.action_date_text DESC NULLS LAST,
                h.load_batch_id DESC,
                h.source_row_number DESC
        ) AS selection_rank
    FROM historical AS h
    JOIN missing_conflicted AS c
      ON c.award_key = h.award_key
)
SELECT
    award_key,
    load_batch_id,
    source_row_number,
    action_date_text,
    listing_code,
    type_code,
    source_fain,
    source_uri
FROM ranked
WHERE selection_rank = 1
ORDER BY award_key;

ROLLBACK;
