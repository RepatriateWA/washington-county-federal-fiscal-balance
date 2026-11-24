
\set ON_ERROR_STOP on
\pset pager off

BEGIN;

SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;
SET LOCAL statement_timeout = '600s';

\echo
\echo '================================================================'
\echo 'ETL-201P STAGE A.3 - CROSS-VINTAGE URI RECONCILIATION'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '================================================================'

\echo
\echo 'SECTION 1 - RAW ASSISTANCE BATCH INVENTORY'

SELECT
    load_batch_id,
    COUNT(*) AS source_rows,
    COUNT(DISTINCT assistance_award_unique_key) AS award_keys,
    MIN(NULLIF(raw_record ->> 'action_date', '')) AS earliest_action_text,
    MAX(NULLIF(raw_record ->> 'action_date', '')) AS latest_action_text
FROM assistance.raw_award_transaction
GROUP BY load_batch_id
ORDER BY load_batch_id;

\echo
\echo 'SECTION 2 - CROSS-VINTAGE URI EXCEPTION CLASSIFICATION'

WITH historical_uri_profile AS MATERIALIZED (
    SELECT
        r.assistance_award_unique_key AS award_key,
        a.award_id_uri AS canonical_uri,
        a.award_id_fain AS canonical_fain,
        a.created_at AS canonical_created_at,
        COUNT(DISTINCT NULLIF(
            BTRIM(r.raw_record ->> 'cfda_number'), ''
        )) AS listing_variants,
        COUNT(DISTINCT NULLIF(
            BTRIM(r.raw_record ->> 'assistance_type_code'), ''
        )) AS type_variants,
        COUNT(DISTINCT NULLIF(
            BTRIM(r.raw_record ->> 'award_id_uri'), ''
        )) AS historical_uri_variants,
        BOOL_OR(
            a.award_id_uri = NULLIF(
                BTRIM(r.raw_record ->> 'award_id_uri'), ''
            )
        ) AS historical_uri_matched
    FROM assistance.raw_award_transaction AS r
    JOIN assistance.award AS a
      ON a.assistance_award_unique_key =
         r.assistance_award_unique_key
    WHERE r.load_batch_id IN (20, 21)
      AND a.award_id_uri IS NOT NULL
    GROUP BY
        r.assistance_award_unique_key,
        a.award_id_uri,
        a.award_id_fain,
        a.created_at
),
exceptions AS MATERIALIZED (
    SELECT *
    FROM historical_uri_profile
    WHERE NOT historical_uri_matched
),
cross_vintage AS MATERIALIZED (
    SELECT
        e.award_key,
        COUNT(r.source_row_number) AS other_source_rows,
        COUNT(DISTINCT r.load_batch_id) AS other_source_batches,
        COUNT(r.source_row_number) FILTER (
            WHERE NULLIF(
                BTRIM(r.raw_record ->> 'award_id_uri'), ''
            ) = e.canonical_uri
        ) AS canonical_uri_matching_rows,
        COUNT(DISTINCT r.load_batch_id) FILTER (
            WHERE NULLIF(
                BTRIM(r.raw_record ->> 'award_id_uri'), ''
            ) = e.canonical_uri
        ) AS canonical_uri_matching_batches,
        COUNT(DISTINCT NULLIF(
            BTRIM(r.raw_record ->> 'award_id_uri'), ''
        )) AS other_uri_variants,
        MIN(r.load_batch_id) FILTER (
            WHERE NULLIF(
                BTRIM(r.raw_record ->> 'award_id_uri'), ''
            ) = e.canonical_uri
        ) AS first_matching_batch,
        MAX(r.load_batch_id) FILTER (
            WHERE NULLIF(
                BTRIM(r.raw_record ->> 'award_id_uri'), ''
            ) = e.canonical_uri
        ) AS last_matching_batch
    FROM exceptions AS e
    LEFT JOIN assistance.raw_award_transaction AS r
      ON r.assistance_award_unique_key = e.award_key
     AND r.load_batch_id NOT IN (20, 21)
    GROUP BY e.award_key
)
SELECT
    COUNT(*) AS historical_uri_exceptions,
    COUNT(*) FILTER (
        WHERE c.canonical_uri_matching_rows > 0
    ) AS supported_by_other_batches,
    COUNT(*) FILTER (
        WHERE c.canonical_uri_matching_rows = 0
    ) AS not_supported_by_other_batches,
    COUNT(*) FILTER (
        WHERE c.canonical_uri_matching_batches > 1
    ) AS supported_by_multiple_other_batches,
    COUNT(*) FILTER (
        WHERE c.other_source_rows = 0
    ) AS no_other_batch_observations,
    COUNT(*) FILTER (
        WHERE c.other_source_rows > 0
          AND c.canonical_uri_matching_rows = 0
    ) AS other_observations_but_no_uri_match,
    COUNT(*) FILTER (
        WHERE e.listing_variants > 1
           OR e.type_variants > 1
    ) AS historical_classification_conflicted,
    SUM(c.canonical_uri_matching_rows)
        AS total_matching_source_observations
FROM exceptions AS e
JOIN cross_vintage AS c
  ON c.award_key = e.award_key;

\echo
\echo 'SECTION 3 - URI SUPPORT BY OTHER SOURCE BATCH'

WITH exceptions AS MATERIALIZED (
    SELECT
        r.assistance_award_unique_key AS award_key,
        a.award_id_uri AS canonical_uri
    FROM assistance.raw_award_transaction AS r
    JOIN assistance.award AS a
      ON a.assistance_award_unique_key =
         r.assistance_award_unique_key
    WHERE r.load_batch_id IN (20, 21)
      AND a.award_id_uri IS NOT NULL
    GROUP BY
        r.assistance_award_unique_key,
        a.award_id_uri
    HAVING NOT BOOL_OR(
        a.award_id_uri = NULLIF(
            BTRIM(r.raw_record ->> 'award_id_uri'), ''
        )
    )
)
SELECT
    r.load_batch_id,
    COUNT(*) AS matching_source_rows,
    COUNT(DISTINCT r.assistance_award_unique_key)
        AS supported_exception_awards,
    MIN(r.raw_record ->> 'action_date') AS earliest_action_text,
    MAX(r.raw_record ->> 'action_date') AS latest_action_text
FROM exceptions AS e
JOIN assistance.raw_award_transaction AS r
  ON r.assistance_award_unique_key = e.award_key
 AND r.load_batch_id NOT IN (20, 21)
 AND NULLIF(
     BTRIM(r.raw_record ->> 'award_id_uri'), ''
 ) = e.canonical_uri
GROUP BY r.load_batch_id
ORDER BY r.load_batch_id;

\echo
\echo 'SECTION 4 - UNSUPPORTED URI EXCEPTIONS (MAX 100)'

WITH exceptions AS MATERIALIZED (
    SELECT
        r.assistance_award_unique_key AS award_key,
        a.award_id_uri AS canonical_uri,
        a.award_id_fain AS canonical_fain,
        a.created_at AS canonical_created_at,
        MIN(NULLIF(
            BTRIM(r.raw_record ->> 'award_id_uri'), ''
        )) AS historical_uri
    FROM assistance.raw_award_transaction AS r
    JOIN assistance.award AS a
      ON a.assistance_award_unique_key =
         r.assistance_award_unique_key
    WHERE r.load_batch_id IN (20, 21)
      AND a.award_id_uri IS NOT NULL
    GROUP BY
        r.assistance_award_unique_key,
        a.award_id_uri,
        a.award_id_fain,
        a.created_at
    HAVING NOT BOOL_OR(
        a.award_id_uri = NULLIF(
            BTRIM(r.raw_record ->> 'award_id_uri'), ''
        )
    )
)
SELECT
    e.award_key,
    e.canonical_fain,
    e.canonical_uri,
    e.historical_uri,
    e.canonical_created_at,
    (
        SELECT COUNT(*)
        FROM assistance.raw_award_transaction AS r
        WHERE r.assistance_award_unique_key = e.award_key
          AND r.load_batch_id NOT IN (20, 21)
    ) AS other_source_rows
FROM exceptions AS e
WHERE NOT EXISTS (
    SELECT 1
    FROM assistance.raw_award_transaction AS r
    WHERE r.assistance_award_unique_key = e.award_key
      AND r.load_batch_id NOT IN (20, 21)
      AND NULLIF(
          BTRIM(r.raw_record ->> 'award_id_uri'), ''
      ) = e.canonical_uri
)
ORDER BY e.award_key
LIMIT 100;

\echo
\echo 'SECTION 5 - HISTORICAL POPULATION GUARDRAILS'

WITH historical AS MATERIALIZED (
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
    (SELECT COUNT(*) FROM assistance.award)
        AS total_canonical_awards,
    COUNT(*) AS historical_awards,
    COUNT(*) FILTER (
        WHERE a.assistance_award_unique_key IS NOT NULL
    ) AS represented_historical_awards,
    COUNT(*) FILTER (
        WHERE a.assistance_award_unique_key IS NULL
          AND h.listing_count <= 1
          AND h.type_count <= 1
    ) AS missing_nonconflicted,
    COUNT(*) FILTER (
        WHERE a.assistance_award_unique_key IS NULL
          AND (
              h.listing_count > 1
              OR h.type_count > 1
          )
    ) AS held_conflicted
FROM historical AS h
LEFT JOIN assistance.award AS a
  ON a.assistance_award_unique_key = h.award_key;

ROLLBACK;

\echo
\echo 'ETL-201P STAGE A.3 COMPLETE - READ ONLY'
