
\set ON_ERROR_STOP on
\pset pager off

BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;
SET LOCAL statement_timeout = '600s';

\echo
\echo '=============================================================='
\echo 'ETL-201P STAGE A.2 - URI PROVENANCE EXCEPTION DIAGNOSIS'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '=============================================================='

-- Build a transaction-local, reusable exception population.
-- No temporary tables or database writes.

\echo
\echo 'SECTION 1 - URI EXCEPTION CATEGORIES'

WITH source_profile AS MATERIALIZED (
    SELECT
        r.assistance_award_unique_key AS award_key,
        COUNT(*) AS source_rows,
        COUNT(DISTINCT r.load_batch_id) AS source_batches,
        COUNT(DISTINCT NULLIF(
            BTRIM(r.raw_record ->> 'cfda_number'), ''
        )) AS listing_variants,
        COUNT(DISTINCT NULLIF(
            BTRIM(r.raw_record ->> 'assistance_type_code'), ''
        )) AS type_variants,
        COUNT(DISTINCT NULLIF(
            BTRIM(r.raw_record ->> 'award_id_uri'), ''
        )) AS uri_variants,
        BOOL_OR(
            a.award_id_uri = NULLIF(
                BTRIM(r.raw_record ->> 'award_id_uri'), ''
            )
        ) AS exact_trimmed_match,
        BOOL_OR(
            LOWER(a.award_id_uri) = LOWER(NULLIF(
                BTRIM(r.raw_record ->> 'award_id_uri'), ''
            ))
        ) AS case_insensitive_match,
        BOOL_OR(
            a.award_id_uri = NULLIF(
                r.raw_record ->> 'award_id_uri', ''
            )
        ) AS raw_exact_match,
        MIN(r.load_batch_id) AS first_batch,
        MAX(r.load_batch_id) AS last_batch
    FROM assistance.raw_award_transaction AS r
    JOIN assistance.award AS a
      ON a.assistance_award_unique_key =
         r.assistance_award_unique_key
    WHERE r.load_batch_id IN (20, 21)
      AND a.award_id_uri IS NOT NULL
    GROUP BY r.assistance_award_unique_key
),
exceptions AS (
    SELECT
        p.*,
        a.award_id_uri,
        a.award_id_fain,
        a.created_at,
        a.updated_at
    FROM source_profile AS p
    JOIN assistance.award AS a
      ON a.assistance_award_unique_key = p.award_key
    WHERE NOT p.exact_trimmed_match
)
SELECT
    COUNT(*) AS uri_exceptions,
    COUNT(*) FILTER (
        WHERE listing_variants > 1 OR type_variants > 1
    ) AS classification_conflicted,
    COUNT(*) FILTER (
        WHERE listing_variants <= 1 AND type_variants <= 1
    ) AS classification_nonconflicted,
    COUNT(*) FILTER (
        WHERE source_batches = 2
    ) AS cross_batch,
    COUNT(*) FILTER (
        WHERE uri_variants = 0
    ) AS no_source_uri,
    COUNT(*) FILTER (
        WHERE uri_variants = 1
    ) AS one_source_uri,
    COUNT(*) FILTER (
        WHERE uri_variants > 1
    ) AS multiple_source_uris,
    COUNT(*) FILTER (
        WHERE case_insensitive_match
    ) AS case_only_possible,
    COUNT(*) FILTER (
        WHERE raw_exact_match
    ) AS raw_exact_matches,
    COUNT(*) FILTER (
        WHERE award_id_fain IS NOT NULL
    ) AS has_canonical_fain,
    MIN(created_at) AS earliest_created_at,
    MAX(created_at) AS latest_created_at
FROM exceptions;

\echo
\echo 'SECTION 2 - URI EXCEPTIONS BY CANONICAL CREATION DATE'

WITH source_profile AS MATERIALIZED (
    SELECT
        r.assistance_award_unique_key AS award_key,
        BOOL_OR(
            a.award_id_uri = NULLIF(
                BTRIM(r.raw_record ->> 'award_id_uri'), ''
            )
        ) AS uri_matched
    FROM assistance.raw_award_transaction AS r
    JOIN assistance.award AS a
      ON a.assistance_award_unique_key =
         r.assistance_award_unique_key
    WHERE r.load_batch_id IN (20, 21)
      AND a.award_id_uri IS NOT NULL
    GROUP BY r.assistance_award_unique_key
)
SELECT
    a.created_at::date AS canonical_creation_date,
    COUNT(*) AS uri_exceptions
FROM source_profile AS p
JOIN assistance.award AS a
  ON a.assistance_award_unique_key = p.award_key
WHERE NOT p.uri_matched
GROUP BY a.created_at::date
ORDER BY canonical_creation_date;

\echo
\echo 'SECTION 3 - FIRST 30 EXCEPTIONS WITH SOURCE URI SAMPLES'

WITH source_profile AS MATERIALIZED (
    SELECT
        r.assistance_award_unique_key AS award_key,
        BOOL_OR(
            a.award_id_uri = NULLIF(
                BTRIM(r.raw_record ->> 'award_id_uri'), ''
            )
        ) AS uri_matched,
        COUNT(DISTINCT NULLIF(
            BTRIM(r.raw_record ->> 'cfda_number'), ''
        )) AS listing_variants,
        COUNT(DISTINCT NULLIF(
            BTRIM(r.raw_record ->> 'assistance_type_code'), ''
        )) AS type_variants
    FROM assistance.raw_award_transaction AS r
    JOIN assistance.award AS a
      ON a.assistance_award_unique_key =
         r.assistance_award_unique_key
    WHERE r.load_batch_id IN (20, 21)
      AND a.award_id_uri IS NOT NULL
    GROUP BY r.assistance_award_unique_key
),
exceptions AS MATERIALIZED (
    SELECT
        p.award_key,
        p.listing_variants,
        p.type_variants
    FROM source_profile AS p
    WHERE NOT p.uri_matched
    ORDER BY p.award_key
    LIMIT 30
)
SELECT
    e.award_key,
    a.award_id_uri AS canonical_uri,
    a.award_id_fain AS canonical_fain,
    a.created_at::date AS canonical_created,
    e.listing_variants,
    e.type_variants,
    r.load_batch_id,
    r.source_row_number,
    r.raw_record ->> 'award_id_uri' AS source_uri,
    r.raw_record ->> 'award_id_fain' AS source_fain
FROM exceptions AS e
JOIN assistance.award AS a
  ON a.assistance_award_unique_key = e.award_key
JOIN assistance.raw_award_transaction AS r
  ON r.assistance_award_unique_key = e.award_key
 AND r.load_batch_id IN (20, 21)
ORDER BY
    e.award_key,
    r.load_batch_id DESC,
    r.source_row_number DESC
LIMIT 100;

ROLLBACK;

\echo
\echo 'ETL-201P STAGE A.2 COMPLETE - READ ONLY'
