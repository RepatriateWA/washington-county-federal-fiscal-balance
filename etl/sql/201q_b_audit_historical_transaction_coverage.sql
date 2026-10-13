
\set ON_ERROR_STOP on
\pset pager off

\echo '================================================================'
\echo 'ETL-201Q STAGE B - HISTORICAL TRANSACTION COVERAGE'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '================================================================'

BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;
SET LOCAL statement_timeout = '900s';

\echo ''
\echo 'SECTION 1 - RAW TRANSACTION KEY PROFILE'

SELECT
    load_batch_id,
    COUNT(*) AS raw_observations,
    COUNT(DISTINCT assistance_transaction_unique_key)
        AS distinct_transaction_keys,
    COUNT(*) FILTER (
        WHERE assistance_transaction_unique_key IS NULL
           OR BTRIM(assistance_transaction_unique_key) = ''
    ) AS missing_transaction_keys
FROM assistance.raw_award_transaction
WHERE load_batch_id IN (20, 21)
GROUP BY load_batch_id
ORDER BY load_batch_id;

\echo ''
\echo 'SECTION 2 - OBSERVATION LINK COVERAGE'

WITH historical AS MATERIALIZED (
    SELECT
        raw_assistance_transaction_id,
        load_batch_id,
        assistance_transaction_unique_key,
        assistance_award_unique_key
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
)
SELECT
    h.load_batch_id,
    COUNT(*) AS raw_observations,
    COUNT(*) FILTER (
        WHERE o.assistance_transaction_id IS NOT NULL
    ) AS linked_observations,
    COUNT(*) FILTER (
        WHERE o.assistance_transaction_id IS NULL
    ) AS unlinked_observations,
    COUNT(DISTINCT h.assistance_transaction_unique_key)
        AS distinct_raw_transaction_keys
FROM historical AS h
LEFT JOIN assistance.award_transaction_observation AS o
  ON o.raw_assistance_transaction_id =
     h.raw_assistance_transaction_id
GROUP BY h.load_batch_id
ORDER BY h.load_batch_id;

\echo ''
\echo 'SECTION 3 - CANONICAL TRANSACTION KEY COVERAGE'

WITH historical_keys AS MATERIALIZED (
    SELECT DISTINCT
        assistance_transaction_unique_key AS transaction_key
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
)
SELECT
    COUNT(*) AS distinct_historical_transaction_keys,
    COUNT(*) FILTER (
        WHERE t.assistance_transaction_id IS NOT NULL
    ) AS keys_with_canonical_transaction,
    COUNT(*) FILTER (
        WHERE t.assistance_transaction_id IS NULL
    ) AS keys_missing_canonical_transaction
FROM historical_keys AS h
LEFT JOIN assistance.award_transaction AS t
  ON t.assistance_transaction_unique_key = h.transaction_key;

\echo ''
\echo 'SECTION 4 - RAW OBSERVATION COVERAGE CATEGORIES'

WITH historical AS MATERIALIZED (
    SELECT
        raw_assistance_transaction_id,
        assistance_transaction_unique_key
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
)
SELECT
    CASE
        WHEN o.assistance_transaction_id IS NOT NULL
            THEN 'OBSERVATION_LINKED'
        WHEN t.assistance_transaction_id IS NOT NULL
            THEN 'CANONICAL_KEY_PRESENT_LINK_MISSING'
        ELSE 'CANONICAL_TRANSACTION_MISSING'
    END AS coverage_category,
    COUNT(*) AS raw_observations,
    COUNT(DISTINCT h.assistance_transaction_unique_key)
        AS distinct_transaction_keys
FROM historical AS h
LEFT JOIN assistance.award_transaction_observation AS o
  ON o.raw_assistance_transaction_id =
     h.raw_assistance_transaction_id
LEFT JOIN assistance.award_transaction AS t
  ON t.assistance_transaction_unique_key =
     h.assistance_transaction_unique_key
GROUP BY 1
ORDER BY 1;

\echo ''
\echo 'SECTION 5 - CANONICAL TRANSACTION/AWARD KEY CONSISTENCY'

WITH historical_keys AS MATERIALIZED (
    SELECT DISTINCT
        assistance_transaction_unique_key AS transaction_key,
        assistance_award_unique_key AS award_key
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
)
SELECT
    COUNT(*) AS historical_transaction_award_pairs,
    COUNT(*) FILTER (
        WHERE t.assistance_transaction_id IS NOT NULL
    ) AS pairs_with_canonical_transaction,
    COUNT(*) FILTER (
        WHERE t.assistance_transaction_id IS NOT NULL
          AND a.assistance_award_unique_key IS DISTINCT FROM
              h.award_key
    ) AS canonical_award_key_mismatches,
    COUNT(*) FILTER (
        WHERE t.assistance_transaction_id IS NOT NULL
          AND a.assistance_award_unique_key = h.award_key
    ) AS canonical_award_key_matches
FROM historical_keys AS h
LEFT JOIN assistance.award_transaction AS t
  ON t.assistance_transaction_unique_key = h.transaction_key
LEFT JOIN assistance.award AS a
  ON a.assistance_award_id = t.assistance_award_id;

ROLLBACK;

\echo ''
\echo 'ETL-201Q STAGE B COMPLETE - READ ONLY'
