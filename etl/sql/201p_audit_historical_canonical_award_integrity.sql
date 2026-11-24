
\set ON_ERROR_STOP on
\pset pager off

BEGIN;

SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;
SET LOCAL statement_timeout = '600s';

\echo
\echo '================================================================'
\echo 'ETL-201P v0.1 - HISTORICAL CANONICAL AWARD INTEGRITY'
\echo 'FY2018 batch 20 / FY2019 batch 21'
\echo 'STAGE A - READ ONLY - NO DATABASE WRITES'
\echo '================================================================'

\echo
\echo 'SECTION 1 - GLOBAL CANONICAL POPULATION'

SELECT
    COUNT(*) AS canonical_awards,
    COUNT(DISTINCT assistance_award_unique_key)
        AS distinct_canonical_keys,
    COUNT(*) FILTER (
        WHERE award_id_fain IS NULL
          AND award_id_uri IS NULL
    ) AS missing_identifiers,
    COUNT(*) FILTER (
        WHERE first_action_date IS NOT NULL
          AND last_action_date IS NOT NULL
          AND first_action_date > last_action_date
    ) AS inverted_action_dates
FROM assistance.award;

\echo
\echo 'SECTION 2 - HISTORICAL SOURCE POPULATION'

WITH historical AS (
    SELECT
        load_batch_id,
        assistance_award_unique_key,
        source_row_number
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
)
SELECT
    COUNT(*) AS historical_source_rows,
    COUNT(*) FILTER (
        WHERE load_batch_id = 20
    ) AS fy2018_source_rows,
    COUNT(*) FILTER (
        WHERE load_batch_id = 21
    ) AS fy2019_source_rows,
    COUNT(DISTINCT assistance_award_unique_key)
        AS distinct_historical_awards,
    COUNT(DISTINCT (load_batch_id, source_row_number))
        AS distinct_source_identities
FROM historical;

\echo
\echo 'SECTION 3 - HISTORICAL REPRESENTATION BY CLASSIFICATION'

WITH historical AS MATERIALIZED (
    SELECT
        assistance_award_unique_key AS award_key,
        COUNT(*) AS source_observations,
        COUNT(DISTINCT NULLIF(
            BTRIM(raw_record ->> 'cfda_number'), ''
        )) AS listing_count,
        COUNT(DISTINCT NULLIF(
            BTRIM(raw_record ->> 'assistance_type_code'), ''
        )) AS type_count,
        COUNT(*) FILTER (
            WHERE load_batch_id = 20
        ) AS fy2018_observations,
        COUNT(*) FILTER (
            WHERE load_batch_id = 21
        ) AS fy2019_observations
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
    GROUP BY assistance_award_unique_key
),
classified AS (
    SELECT
        h.*,
        (h.listing_count > 1 OR h.type_count > 1)
            AS has_classification_conflict,
        (a.assistance_award_unique_key IS NOT NULL)
            AS is_canonical
    FROM historical AS h
    LEFT JOIN assistance.award AS a
      ON a.assistance_award_unique_key = h.award_key
)
SELECT
    COUNT(*) AS historical_awards,
    COUNT(*) FILTER (
        WHERE is_canonical
    ) AS represented_awards,
    COUNT(*) FILTER (
        WHERE NOT is_canonical
    ) AS missing_awards,
    COUNT(*) FILTER (
        WHERE is_canonical
          AND NOT has_classification_conflict
    ) AS represented_nonconflicted,
    COUNT(*) FILTER (
        WHERE is_canonical
          AND has_classification_conflict
    ) AS represented_conflicted,
    COUNT(*) FILTER (
        WHERE NOT is_canonical
          AND NOT has_classification_conflict
    ) AS missing_nonconflicted,
    COUNT(*) FILTER (
        WHERE NOT is_canonical
          AND has_classification_conflict
    ) AS held_conflicted,
    SUM(source_observations) FILTER (
        WHERE is_canonical
    ) AS represented_source_observations,
    SUM(source_observations) FILTER (
        WHERE NOT is_canonical
    ) AS held_source_observations
FROM classified;

\echo
\echo 'SECTION 4 - CANONICAL IDENTIFIER PROVENANCE'

WITH historical_keys AS MATERIALIZED (
    SELECT DISTINCT
        assistance_award_unique_key AS award_key
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
),
source_identifiers AS MATERIALIZED (
    SELECT DISTINCT
        r.assistance_award_unique_key AS award_key,
        NULLIF(
            BTRIM(r.raw_record ->> 'award_id_fain'), ''
        ) AS source_fain,
        NULLIF(
            BTRIM(r.raw_record ->> 'award_id_uri'), ''
        ) AS source_uri
    FROM assistance.raw_award_transaction AS r
    JOIN historical_keys AS h
      ON h.award_key = r.assistance_award_unique_key
    WHERE r.load_batch_id IN (20, 21)
),
represented AS (
    SELECT
        a.assistance_award_unique_key AS award_key,
        a.award_id_fain,
        a.award_id_uri
    FROM assistance.award AS a
    JOIN historical_keys AS h
      ON h.award_key = a.assistance_award_unique_key
)
SELECT
    COUNT(*) AS represented_awards,
    COUNT(*) FILTER (
        WHERE a.award_id_fain IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM source_identifiers AS s
              WHERE s.award_key = a.award_key
                AND s.source_fain = a.award_id_fain
          )
    ) AS fain_without_source_match,
    COUNT(*) FILTER (
        WHERE a.award_id_uri IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM source_identifiers AS s
              WHERE s.award_key = a.award_key
                AND s.source_uri = a.award_id_uri
          )
    ) AS uri_without_source_match
FROM represented AS a;

\echo
\echo 'SECTION 5 - CLASSIFICATION REFERENCE INTEGRITY'

WITH historical_keys AS MATERIALIZED (
    SELECT DISTINCT
        assistance_award_unique_key AS award_key
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
),
represented AS (
    SELECT a.*
    FROM assistance.award AS a
    JOIN historical_keys AS h
      ON h.award_key = a.assistance_award_unique_key
)
SELECT
    COUNT(*) AS represented_awards,
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
    ) AS missing_action_date_range
FROM represented;

\echo
\echo 'SECTION 6 - HISTORICAL SOURCE YEAR OVERLAP'

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
\echo 'SECTION 7 - ENFORCED CERTIFICATION ASSERTIONS'

DO $audit$
DECLARE
    v_total BIGINT;
    v_source_rows BIGINT;
    v_distinct_keys BIGINT;
    v_represented BIGINT;
    v_held BIGINT;
    v_missing_nonconflicted BIGINT;
BEGIN
    SELECT COUNT(*)
    INTO v_total
    FROM assistance.award;

    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_award_unique_key)
    INTO v_source_rows, v_distinct_keys
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21);

    WITH historical AS (
        SELECT
            assistance_award_unique_key AS award_key,
            COUNT(DISTINCT NULLIF(
                BTRIM(raw_record ->> 'cfda_number'), ''
            )) AS listing_count,
            COUNT(DISTINCT NULLIF(
                BTRIM(raw_record ->> 'assistance_type_code'), ''
            )) AS type_count
        FROM assistance.raw_award_transaction
        WHERE load_batch_id IN (20, 21)
        GROUP BY assistance_award_unique_key
    )
    SELECT
        COUNT(*) FILTER (
            WHERE a.assistance_award_unique_key IS NOT NULL
        ),
        COUNT(*) FILTER (
            WHERE a.assistance_award_unique_key IS NULL
              AND (
                  h.listing_count > 1
                  OR h.type_count > 1
              )
        ),
        COUNT(*) FILTER (
            WHERE a.assistance_award_unique_key IS NULL
              AND h.listing_count <= 1
              AND h.type_count <= 1
        )
    INTO
        v_represented,
        v_held,
        v_missing_nonconflicted
    FROM historical AS h
    LEFT JOIN assistance.award AS a
      ON a.assistance_award_unique_key = h.award_key;

    IF v_total <> 968547 THEN
        RAISE EXCEPTION
            'Canonical population mismatch: %', v_total;
    END IF;

    IF v_source_rows <> 208187 THEN
        RAISE EXCEPTION
            'Historical source row mismatch: %', v_source_rows;
    END IF;

    IF v_distinct_keys <> 166710 THEN
        RAISE EXCEPTION
            'Historical distinct key mismatch: %', v_distinct_keys;
    END IF;

    IF v_represented <> 166620 THEN
        RAISE EXCEPTION
            'Historical representation mismatch: %', v_represented;
    END IF;

    IF v_held <> 90 THEN
        RAISE EXCEPTION
            'Held classification conflicts mismatch: %', v_held;
    END IF;

    IF v_missing_nonconflicted <> 0 THEN
        RAISE EXCEPTION
            'Missing nonconflicted awards: %',
            v_missing_nonconflicted;
    END IF;

    RAISE NOTICE
        'ETL-201P STAGE A ASSERTIONS: PASS';

    RAISE NOTICE
        'Canonical awards: %', v_total;

    RAISE NOTICE
        'Historical source observations: %', v_source_rows;

    RAISE NOTICE
        'Historical represented awards: %', v_represented;

    RAISE NOTICE
        'Held classification conflicts: %', v_held;
END
$audit$;

ROLLBACK;

\echo
\echo 'ETL-201P STAGE A COMPLETE - READ ONLY'
