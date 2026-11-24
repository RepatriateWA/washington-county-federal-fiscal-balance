
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-212R v0.1 - HISTORICAL PROCUREMENT REFERENTIAL PREFLIGHT'
\echo 'FY2018-FY2019 - STRICTLY READ ONLY'
\echo '============================================================'

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SET LOCAL statement_timeout = '120s';
SET LOCAL max_parallel_workers_per_gather = 0;

\echo ''
\echo '1. TRANSACTION KEY MATCH CARDINALITY'

WITH raw_keys AS MATERIALIZED (
    SELECT
        raw.raw_award_transaction_id,
        raw.load_batch_id,
        NULLIF(
            BTRIM(
                raw.raw_record ->>
                'contract_transaction_unique_key'
            ),
            ''
        ) AS transaction_key
    FROM procurement.raw_award_transaction AS raw
    WHERE raw.load_batch_id IN (22, 23)
),
key_counts AS MATERIALIZED (
    SELECT
        raw.load_batch_id,
        raw.raw_award_transaction_id,
        raw.transaction_key,
        COUNT(at.award_transaction_id) AS matches
    FROM raw_keys AS raw
    LEFT JOIN procurement.award_transaction AS at
      ON at.usaspending_transaction_id = raw.transaction_key
    GROUP BY
        raw.load_batch_id,
        raw.raw_award_transaction_id,
        raw.transaction_key
)
SELECT
    load_batch_id,
    COUNT(*) AS raw_rows,
    COUNT(*) FILTER (
        WHERE transaction_key IS NULL
    ) AS null_transaction_keys,
    COUNT(*) FILTER (
        WHERE matches = 0
    ) AS unmatched,
    COUNT(*) FILTER (
        WHERE matches = 1
    ) AS exactly_one_match,
    COUNT(*) FILTER (
        WHERE matches > 1
    ) AS multiple_matches,
    MAX(matches) AS maximum_matches
FROM key_counts
GROUP BY load_batch_id
ORDER BY load_batch_id;

\echo ''
\echo '2. CANONICAL TRANSACTION KEY UNIQUENESS'

SELECT
    COUNT(*) AS duplicate_transaction_keys
FROM (
    SELECT usaspending_transaction_id
    FROM procurement.award_transaction
    WHERE usaspending_transaction_id IS NOT NULL
    GROUP BY usaspending_transaction_id
    HAVING COUNT(*) > 1
) AS duplicates;

\echo ''
\echo '3. EXISTING HISTORICAL PLACE RELATIONSHIPS'

WITH historical AS MATERIALIZED (
    SELECT
        raw.load_batch_id,
        at.award_transaction_id
    FROM procurement.raw_award_transaction AS raw
    JOIN procurement.award_transaction AS at
      ON at.usaspending_transaction_id =
         raw.raw_record ->>
         'contract_transaction_unique_key'
    WHERE raw.load_batch_id IN (22, 23)
)
SELECT
    h.load_batch_id,
    COUNT(*) AS matched_transactions,
    COUNT(pop.place_of_performance_id)
        AS existing_place_relationships,
    COUNT(*) FILTER (
        WHERE pop.place_of_performance_id IS NULL
    ) AS missing_place_relationships,
    COUNT(*) FILTER (
        WHERE pop.place_of_performance_id IS NOT NULL
          AND pop.place_id IS NULL
    ) AS existing_relationships_without_place_id
FROM historical AS h
LEFT JOIN procurement.place_of_performance AS pop
  ON pop.award_transaction_id = h.award_transaction_id
GROUP BY h.load_batch_id
ORDER BY h.load_batch_id;

\echo ''
\echo '4. HISTORICAL CANONICAL TRANSACTION DUPLICATION'

WITH historical AS MATERIALIZED (
    SELECT
        raw.raw_award_transaction_id,
        at.award_transaction_id
    FROM procurement.raw_award_transaction AS raw
    JOIN procurement.award_transaction AS at
      ON at.usaspending_transaction_id =
         raw.raw_record ->>
         'contract_transaction_unique_key'
    WHERE raw.load_batch_id IN (22, 23)
)
SELECT
    COUNT(*) AS canonical_transactions_with_multiple_raw_rows
FROM (
    SELECT award_transaction_id
    FROM historical
    GROUP BY award_transaction_id
    HAVING COUNT(*) > 1
) AS duplicates;

\echo ''
\echo '5. PLACE-OF-PERFORMANCE CONSTRAINTS'

SELECT
    con.conname AS constraint_name,
    con.contype AS constraint_type,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint AS con
WHERE con.conrelid =
    'procurement.place_of_performance'::regclass
ORDER BY con.conname;

\echo ''
\echo '6. PLACE-OF-PERFORMANCE COLUMNS'

SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'procurement'
  AND table_name = 'place_of_performance'
ORDER BY ordinal_position;

\echo ''
\echo '7. PLACE-OF-PERFORMANCE UNIQUE INDEXES'

SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'procurement'
  AND tablename = 'place_of_performance'
  AND indexdef ILIKE '%UNIQUE%'
ORDER BY indexname;

\echo ''
\echo '8. CANONICAL PLACE INSERTION METADATA'

SELECT
    column_name,
    data_type,
    is_nullable,
    column_default,
    is_identity,
    identity_generation,
    is_generated
FROM information_schema.columns
WHERE table_schema = 'procurement'
  AND table_name = 'place'
ORDER BY ordinal_position;

\echo ''
\echo '9. CANONICAL PLACE UNIQUENESS CONSTRAINTS'

SELECT
    con.conname,
    con.contype,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint AS con
WHERE con.conrelid = 'procurement.place'::regclass
  AND con.contype IN ('p', 'u', 'c')
ORDER BY con.conname;

ROLLBACK;

\echo ''
\echo 'ETL-212R v0.1 COMPLETE - NO DATABASE WRITES'
