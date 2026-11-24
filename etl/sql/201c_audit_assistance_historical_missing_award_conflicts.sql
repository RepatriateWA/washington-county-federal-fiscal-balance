
\set ON_ERROR_STOP on

BEGIN;
SET TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '120s';

\echo ''
\echo '============================================================'
\echo 'WCFFBP - ETL-201C v0.1'
\echo 'HISTORICAL MISSING-AWARD CONFLICT RESOLUTION AUDIT'
\echo 'FY2018 batch 20 / FY2019 batch 21'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

\echo ''
\echo 'SECTION 1 - INSERTION ELIGIBILITY PROFILE'
\echo ''

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
            BTRIM(raw.raw_record ->> 'award_id_fain'), ''
        ) AS source_fain,
        NULLIF(
            BTRIM(raw.raw_record ->> 'award_id_uri'), ''
        ) AS source_uri,
        LEFT(
            BTRIM(raw.raw_record ->> 'action_date'), 10
        ) AS action_date_text
    FROM assistance.raw_award_transaction AS raw
    WHERE raw.load_batch_id IN (20, 21)
),
missing AS MATERIALIZED (
    SELECT h.*
    FROM historical AS h
    WHERE NOT EXISTS (
        SELECT 1
        FROM assistance.award AS a
        WHERE a.assistance_award_unique_key = h.award_key
    )
),
resolved AS (
    SELECT
        m.*,
        l.assistance_listing_id,
        t.assistance_type_id,
        CASE
            WHEN action_date_text ~
                 '^\d{4}-\d{2}-\d{2}$'
            THEN action_date_text::date
            ELSE NULL
        END AS action_date
    FROM missing AS m
    LEFT JOIN assistance.assistance_listing AS l
      ON l.cfda_number = m.listing_code
    LEFT JOIN assistance.assistance_type AS t
      ON t.assistance_type_code = m.type_code
),
profile AS (
    SELECT
        award_key,
        COUNT(*) AS observation_count,
        COUNT(DISTINCT load_batch_id) AS batch_count,
        COUNT(DISTINCT listing_code) AS listing_variants,
        COUNT(DISTINCT type_code) AS type_variants,
        COUNT(DISTINCT assistance_listing_id)
            AS resolved_listing_variants,
        COUNT(DISTINCT assistance_type_id)
            AS resolved_type_variants,
        COUNT(DISTINCT action_date) AS date_count,
        BOOL_OR(
            assistance_listing_id IS NULL
            OR assistance_type_id IS NULL
            OR action_date IS NULL
            OR (
                source_fain IS NULL
                AND source_uri IS NULL
            )
        ) AS has_incomplete_observation
    FROM resolved
    GROUP BY award_key
),
ranked AS (
    SELECT
        r.*,
        ROW_NUMBER() OVER (
            PARTITION BY award_key
            ORDER BY
                action_date DESC NULLS LAST,
                load_batch_id DESC,
                source_row_number DESC
        ) AS selection_rank,
        MAX(action_date) OVER (
            PARTITION BY award_key
        ) AS latest_date
    FROM resolved AS r
),
latest_profile AS (
    SELECT
        award_key,
        COUNT(*) AS latest_observations,
        COUNT(DISTINCT assistance_listing_id)
            AS latest_listing_variants,
        COUNT(DISTINCT assistance_type_id)
            AS latest_type_variants
    FROM ranked
    WHERE action_date = latest_date
    GROUP BY award_key
),
combined AS (
    SELECT
        p.*,
        COALESCE(lp.latest_observations, 0)
            AS latest_observations,
        COALESCE(lp.latest_listing_variants, 0)
            AS latest_listing_variants,
        COALESCE(lp.latest_type_variants, 0)
            AS latest_type_variants
    FROM profile AS p
    LEFT JOIN latest_profile AS lp USING (award_key)
)
SELECT
    COUNT(*) AS missing_awards,

    COUNT(*) FILTER (
        WHERE listing_variants > 1
    ) AS source_listing_conflicts,

    COUNT(*) FILTER (
        WHERE type_variants > 1
    ) AS source_type_conflicts,

    COUNT(*) FILTER (
        WHERE resolved_listing_variants > 1
    ) AS resolved_listing_conflicts,

    COUNT(*) FILTER (
        WHERE resolved_type_variants > 1
    ) AS resolved_type_conflicts,

    COUNT(*) FILTER (
        WHERE listing_variants > 1
           OR type_variants > 1
    ) AS any_source_conflict,

    COUNT(*) FILTER (
        WHERE resolved_listing_variants > 1
           OR resolved_type_variants > 1
    ) AS any_resolved_conflict,

    COUNT(*) FILTER (
        WHERE (
            resolved_listing_variants > 1
            OR resolved_type_variants > 1
        )
        AND batch_count = 2
    ) AS crossyear_resolved_conflicts,

    COUNT(*) FILTER (
        WHERE latest_listing_variants > 1
           OR latest_type_variants > 1
    ) AS latest_date_conflicts,

    COUNT(*) FILTER (
        WHERE latest_observations > 1
    ) AS latest_date_ties,

    COUNT(*) FILTER (
        WHERE has_incomplete_observation
    ) AS incomplete_awards,

    COUNT(*) FILTER (
        WHERE NOT has_incomplete_observation
          AND resolved_listing_variants = 1
          AND resolved_type_variants = 1
    ) AS unambiguous_candidates,

    COUNT(*) FILTER (
        WHERE has_incomplete_observation
           OR resolved_listing_variants > 1
           OR resolved_type_variants > 1
    ) AS review_candidates

FROM combined;

\echo ''
\echo 'SECTION 2 - CLASSIFICATION CONFLICT DETAILS'
\echo 'Sample: first 25 conflicting missing award keys'
\echo ''

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
        LEFT(
            BTRIM(raw.raw_record ->> 'action_date'), 10
        ) AS action_date_text
    FROM assistance.raw_award_transaction AS raw
    WHERE raw.load_batch_id IN (20, 21)
),
missing AS MATERIALIZED (
    SELECT h.*
    FROM historical AS h
    WHERE NOT EXISTS (
        SELECT 1
        FROM assistance.award AS a
        WHERE a.assistance_award_unique_key = h.award_key
    )
),
conflicts AS (
    SELECT
        award_key
    FROM missing
    GROUP BY award_key
    HAVING COUNT(DISTINCT listing_code) > 1
        OR COUNT(DISTINCT type_code) > 1
),
sample_keys AS (
    SELECT award_key
    FROM conflicts
    ORDER BY award_key
    LIMIT 25
),
ranked AS (
    SELECT
        m.*,
        ROW_NUMBER() OVER (
            PARTITION BY m.award_key
            ORDER BY
                m.action_date_text DESC NULLS LAST,
                m.load_batch_id DESC,
                m.source_row_number DESC
        ) AS selection_rank
    FROM missing AS m
    JOIN sample_keys AS s USING (award_key)
)
SELECT
    award_key,
    load_batch_id,
    source_row_number,
    action_date_text,
    listing_code,
    type_code,
    CASE
        WHEN selection_rank = 1
        THEN 'SELECTED'
        ELSE 'OTHER'
    END AS selection_status
FROM ranked
ORDER BY award_key, selection_rank;

ROLLBACK;
