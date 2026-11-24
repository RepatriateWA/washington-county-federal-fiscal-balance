
\set ON_ERROR_STOP on

BEGIN;
SET TRANSACTION READ ONLY;

\echo '============================================================'
\echo 'WCFFBP - HISTORICAL AWARD INSERTION CERTIFICATION v0.1'
\echo 'FY2018 batch 20 / FY2019 batch 21'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

WITH missing AS (
    SELECT
        raw.load_batch_id,
        raw.source_row_number,
        raw.assistance_award_unique_key,
        CASE
            WHEN LEFT(
                BTRIM(raw.raw_record ->> 'action_date'), 10
            ) ~ '^\d{4}-\d{2}-\d{2}$'
            THEN LEFT(
                BTRIM(raw.raw_record ->> 'action_date'), 10
            )::date
            ELSE NULL
        END AS action_date,
        NULLIF(
            BTRIM(raw.raw_record ->> 'award_id_fain'), ''
        ) AS source_fain,
        NULLIF(
            BTRIM(raw.raw_record ->> 'award_id_uri'), ''
        ) AS source_uri,
        listing.assistance_listing_id,
        assistance_type.assistance_type_id
    FROM assistance.raw_award_transaction AS raw
    LEFT JOIN assistance.award AS existing
      ON existing.assistance_award_unique_key =
         raw.assistance_award_unique_key
    LEFT JOIN assistance.assistance_listing AS listing
      ON listing.cfda_number =
         BTRIM(raw.raw_record ->> 'cfda_number')
    LEFT JOIN assistance.assistance_type AS assistance_type
      ON assistance_type.assistance_type_code =
         BTRIM(raw.raw_record ->> 'assistance_type_code')
    WHERE raw.load_batch_id IN (20, 21)
      AND existing.assistance_award_id IS NULL
),
key_profile AS (
    SELECT
        assistance_award_unique_key,
        COUNT(*) AS observation_count,
        COUNT(DISTINCT load_batch_id) AS batch_count,
        COUNT(DISTINCT assistance_listing_id)
            AS listing_variants,
        COUNT(DISTINCT assistance_type_id)
            AS type_variants,
        COUNT(DISTINCT source_fain)
            AS fain_variants,
        COUNT(DISTINCT source_uri)
            AS uri_variants,
        BOOL_OR(
            assistance_listing_id IS NULL
            OR assistance_type_id IS NULL
            OR (
                source_fain IS NULL
                AND source_uri IS NULL
            )
        ) AS any_incomplete_observation
    FROM missing
    GROUP BY assistance_award_unique_key
),
ranked AS (
    SELECT
        missing.*,
        ROW_NUMBER() OVER (
            PARTITION BY assistance_award_unique_key
            ORDER BY
                action_date DESC NULLS LAST,
                load_batch_id DESC,
                source_row_number DESC
        ) AS selection_rank
    FROM missing
),
selected AS (
    SELECT *
    FROM ranked
    WHERE selection_rank = 1
)
SELECT
    (SELECT COUNT(*) FROM missing)
        AS raw_observations,

    (SELECT COUNT(*) FROM key_profile)
        AS distinct_missing_keys,

    (SELECT COUNT(*)
     FROM key_profile
     WHERE batch_count = 2)
        AS crossyear_keys,

    (SELECT COUNT(*)
     FROM missing
     WHERE assistance_award_unique_key IS NULL)
        AS null_key_observations,

    (SELECT COUNT(*)
     FROM selected
     WHERE assistance_listing_id IS NULL)
        AS selected_missing_listing,

    (SELECT COUNT(*)
     FROM selected
     WHERE assistance_type_id IS NULL)
        AS selected_missing_type,

    (SELECT COUNT(*)
     FROM selected
     WHERE source_fain IS NULL
       AND source_uri IS NULL)
        AS selected_missing_identifier,

    (SELECT COUNT(*)
     FROM selected
     WHERE action_date IS NULL)
        AS selected_missing_action_date,

    (SELECT COUNT(*)
     FROM key_profile
     WHERE listing_variants > 1)
        AS keys_with_listing_conflict,

    (SELECT COUNT(*)
     FROM key_profile
     WHERE type_variants > 1)
        AS keys_with_type_conflict,

    (SELECT COUNT(*)
     FROM key_profile
     WHERE fain_variants > 1)
        AS keys_with_fain_conflict,

    (SELECT COUNT(*)
     FROM key_profile
     WHERE uri_variants > 1)
        AS keys_with_uri_conflict,

    (SELECT COUNT(*)
     FROM key_profile
     WHERE any_incomplete_observation)
        AS keys_with_incomplete_observation;

ROLLBACK;
