
\set ON_ERROR_STOP on
\pset pager off

BEGIN;

SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;
SET LOCAL statement_timeout = '600s';

\echo
\echo '================================================================'
\echo 'ETL-201P STAGE B.1 - HISTORICAL INSERTION COHORT'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '================================================================'

\echo
\echo 'SECTION 1 - HISTORICAL CANONICAL CREATION-DATE PROFILE'

WITH historical_keys AS MATERIALIZED (
    SELECT DISTINCT assistance_award_unique_key AS award_key
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
)
SELECT
    a.created_at::date AS creation_date,
    COUNT(*) AS historical_canonical_awards,
    MIN(a.created_at) AS first_created_at,
    MAX(a.created_at) AS last_created_at
FROM historical_keys AS h
JOIN assistance.award AS a
  ON a.assistance_award_unique_key = h.award_key
GROUP BY a.created_at::date
ORDER BY creation_date;

\echo
\echo 'SECTION 2 - RECENT CREATION-TIME CLUSTERS'

WITH historical_keys AS MATERIALIZED (
    SELECT DISTINCT assistance_award_unique_key AS award_key
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
)
SELECT
    date_trunc('minute', a.created_at) AS creation_minute,
    COUNT(*) AS historical_canonical_awards,
    MIN(a.created_at) AS first_created_at,
    MAX(a.created_at) AS last_created_at
FROM historical_keys AS h
JOIN assistance.award AS a
  ON a.assistance_award_unique_key = h.award_key
WHERE a.created_at >= TIMESTAMP '2026-10-01'
GROUP BY date_trunc('minute', a.created_at)
ORDER BY creation_minute;

\echo
\echo 'SECTION 3 - HISTORICAL COHORT BEFORE/AFTER OCTOBER 1'

WITH historical_keys AS MATERIALIZED (
    SELECT DISTINCT assistance_award_unique_key AS award_key
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
)
SELECT
    COUNT(*) AS represented_historical_awards,
    COUNT(*) FILTER (
        WHERE a.created_at < TIMESTAMP '2026-10-01'
    ) AS created_before_october,
    COUNT(*) FILTER (
        WHERE a.created_at >= TIMESTAMP '2026-10-01'
    ) AS created_october_or_later,
    COUNT(*) FILTER (
        WHERE a.created_at IS NULL
    ) AS missing_creation_timestamp,
    MIN(a.created_at) AS earliest_creation,
    MAX(a.created_at) AS latest_creation
FROM historical_keys AS h
JOIN assistance.award AS a
  ON a.assistance_award_unique_key = h.award_key;

\echo
\echo 'SECTION 4 - HISTORICAL CLASSIFICATION AND CREATION COHORT'

WITH historical_profile AS MATERIALIZED (
    SELECT
        assistance_award_unique_key AS award_key,
        COUNT(DISTINCT NULLIF(
            BTRIM(raw_record ->> 'cfda_number'), ''
        )) AS listing_variants,
        COUNT(DISTINCT NULLIF(
            BTRIM(raw_record ->> 'assistance_type_code'), ''
        )) AS type_variants
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
    GROUP BY assistance_award_unique_key
)
SELECT
    CASE
        WHEN a.created_at IS NULL THEN 'NOT_REPRESENTED'
        WHEN a.created_at < TIMESTAMP '2026-10-01'
            THEN 'CREATED_BEFORE_OCTOBER'
        ELSE 'CREATED_OCTOBER_OR_LATER'
    END AS creation_cohort,
    CASE
        WHEN h.listing_variants > 1
          OR h.type_variants > 1
            THEN 'CLASSIFICATION_CONFLICT'
        ELSE 'NONCONFLICTED'
    END AS historical_classification,
    COUNT(*) AS award_keys
FROM historical_profile AS h
LEFT JOIN assistance.award AS a
  ON a.assistance_award_unique_key = h.award_key
GROUP BY 1, 2
ORDER BY 1, 2;

\echo
\echo 'SECTION 5 - CANONICAL POPULATION GUARDRAILS'

SELECT
    COUNT(*) AS total_canonical_awards,
    COUNT(DISTINCT assistance_award_unique_key)
        AS distinct_canonical_keys,
    COUNT(*) FILTER (
        WHERE assistance_award_unique_key IS NULL
    ) AS null_canonical_keys
FROM assistance.award;

ROLLBACK;

\echo
\echo 'ETL-201P STAGE B.1 COMPLETE - READ ONLY'
