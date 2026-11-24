
\set ON_ERROR_STOP on
\pset pager off

BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;
SET LOCAL statement_timeout = '600s';

\echo
\echo '=============================================================='
\echo 'ETL-201P STAGE A.1 - HISTORICAL PROVENANCE RECOVERY'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '=============================================================='

\echo
\echo 'SECTION 1 - MATERIALIZE HISTORICAL PROVENANCE AUDIT'

-- Temporary tables are not permitted in READ ONLY transactions.
-- Use a single materialized CTE to avoid repeated correlated probes.

WITH source_matches AS MATERIALIZED (
    SELECT
        a.assistance_award_unique_key AS award_key,
        BOOL_OR(
            a.award_id_fain IS NOT NULL
            AND NULLIF(
                BTRIM(r.raw_record ->> 'award_id_fain'), ''
            ) = a.award_id_fain
        ) AS fain_matched,
        BOOL_OR(
            a.award_id_uri IS NOT NULL
            AND NULLIF(
                BTRIM(r.raw_record ->> 'award_id_uri'), ''
            ) = a.award_id_uri
        ) AS uri_matched,
        COUNT(*) AS source_observations,
        COUNT(DISTINCT r.load_batch_id) AS source_batches
    FROM assistance.raw_award_transaction AS r
    JOIN assistance.award AS a
      ON a.assistance_award_unique_key =
         r.assistance_award_unique_key
    WHERE r.load_batch_id IN (20, 21)
    GROUP BY
        a.assistance_award_unique_key
),
audit AS (
    SELECT
        a.assistance_award_unique_key,
        a.award_id_fain,
        a.award_id_uri,
        a.assistance_listing_id,
        a.assistance_type_id,
        a.first_action_date,
        a.last_action_date,
        s.fain_matched,
        s.uri_matched,
        s.source_observations,
        s.source_batches
    FROM source_matches AS s
    JOIN assistance.award AS a
      ON a.assistance_award_unique_key = s.award_key
)
SELECT
    COUNT(*) AS represented_historical_awards,
    COALESCE(SUM(source_observations), 0)
        AS represented_source_observations,
    COUNT(*) FILTER (
        WHERE award_id_fain IS NOT NULL
          AND NOT fain_matched
    ) AS fain_without_source_match,
    COUNT(*) FILTER (
        WHERE award_id_uri IS NOT NULL
          AND NOT uri_matched
    ) AS uri_without_source_match,
    COUNT(*) FILTER (
        WHERE assistance_listing_id IS NULL
    ) AS missing_listing_id,
    COUNT(*) FILTER (
        WHERE assistance_type_id IS NULL
    ) AS missing_type_id,
    COUNT(*) FILTER (
        WHERE award_id_fain IS NULL
          AND award_id_uri IS NULL
    ) AS missing_identifiers,
    COUNT(*) FILTER (
        WHERE first_action_date IS NULL
           OR last_action_date IS NULL
    ) AS missing_action_date_range,
    COUNT(*) FILTER (
        WHERE source_batches = 2
    ) AS represented_cross_batch_awards
FROM audit;

\echo
\echo 'SECTION 2 - SOURCE YEAR OVERLAP'

WITH historical AS (
    SELECT
        assistance_award_unique_key AS award_key,
        BOOL_OR(load_batch_id = 20) AS in_fy2018,
        BOOL_OR(load_batch_id = 21) AS in_fy2019
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
    GROUP BY assistance_award_unique_key
)
SELECT
    COUNT(*) FILTER (
        WHERE in_fy2018 AND NOT in_fy2019
    ) AS fy2018_only_awards,
    COUNT(*) FILTER (
        WHERE in_fy2019 AND NOT in_fy2018
    ) AS fy2019_only_awards,
    COUNT(*) FILTER (
        WHERE in_fy2018 AND in_fy2019
    ) AS cross_year_awards,
    COUNT(*) AS total_historical_awards
FROM historical;

\echo
\echo 'SECTION 3 - ENFORCED PROVENANCE ASSERTIONS'

DO $audit$
DECLARE
    v_represented BIGINT;
    v_source_rows BIGINT;
    v_bad_fain BIGINT;
    v_bad_uri BIGINT;
    v_missing_listing BIGINT;
    v_missing_type BIGINT;
    v_missing_identifiers BIGINT;
    v_missing_dates BIGINT;
BEGIN
    WITH source_matches AS MATERIALIZED (
        SELECT
            a.assistance_award_unique_key AS award_key,
            BOOL_OR(
                a.award_id_fain IS NOT NULL
                AND NULLIF(
                    BTRIM(r.raw_record ->> 'award_id_fain'), ''
                ) = a.award_id_fain
            ) AS fain_matched,
            BOOL_OR(
                a.award_id_uri IS NOT NULL
                AND NULLIF(
                    BTRIM(r.raw_record ->> 'award_id_uri'), ''
                ) = a.award_id_uri
            ) AS uri_matched,
            COUNT(*) AS source_observations
        FROM assistance.raw_award_transaction AS r
        JOIN assistance.award AS a
          ON a.assistance_award_unique_key =
             r.assistance_award_unique_key
        WHERE r.load_batch_id IN (20, 21)
        GROUP BY a.assistance_award_unique_key
    )
    SELECT
        COUNT(*),
        COALESCE(SUM(s.source_observations), 0),
        COUNT(*) FILTER (
            WHERE a.award_id_fain IS NOT NULL
              AND NOT s.fain_matched
        ),
        COUNT(*) FILTER (
            WHERE a.award_id_uri IS NOT NULL
              AND NOT s.uri_matched
        ),
        COUNT(*) FILTER (
            WHERE a.assistance_listing_id IS NULL
        ),
        COUNT(*) FILTER (
            WHERE a.assistance_type_id IS NULL
        ),
        COUNT(*) FILTER (
            WHERE a.award_id_fain IS NULL
              AND a.award_id_uri IS NULL
        ),
        COUNT(*) FILTER (
            WHERE a.first_action_date IS NULL
               OR a.last_action_date IS NULL
        )
    INTO
        v_represented,
        v_source_rows,
        v_bad_fain,
        v_bad_uri,
        v_missing_listing,
        v_missing_type,
        v_missing_identifiers,
        v_missing_dates
    FROM source_matches AS s
    JOIN assistance.award AS a
      ON a.assistance_award_unique_key = s.award_key;

    IF v_represented <> 166620 THEN
        RAISE EXCEPTION
            'Represented award mismatch: %', v_represented;
    END IF;

    IF v_source_rows <> 207343 THEN
        RAISE EXCEPTION
            'Represented source observation mismatch: %',
            v_source_rows;
    END IF;

    IF v_bad_fain <> 0 OR v_bad_uri <> 0 THEN
        RAISE EXCEPTION
            'Identifier provenance failures: FAIN %, URI %',
            v_bad_fain, v_bad_uri;
    END IF;

    IF v_missing_listing <> 0
       OR v_missing_type <> 0
       OR v_missing_identifiers <> 0
       OR v_missing_dates <> 0 THEN
        RAISE EXCEPTION
            'Canonical integrity failures: listing %, type %, identifiers %, dates %',
            v_missing_listing,
            v_missing_type,
            v_missing_identifiers,
            v_missing_dates;
    END IF;

    RAISE NOTICE
        'ETL-201P STAGE A.1 ASSERTIONS: PASS';
    RAISE NOTICE
        'Represented historical awards: %', v_represented;
    RAISE NOTICE
        'Represented source observations: %', v_source_rows;
    RAISE NOTICE
        'FAIN provenance mismatches: %', v_bad_fain;
    RAISE NOTICE
        'URI provenance mismatches: %', v_bad_uri;
END
$audit$;

ROLLBACK;

\echo
\echo 'ETL-201P STAGE A.1 COMPLETE - READ ONLY'
