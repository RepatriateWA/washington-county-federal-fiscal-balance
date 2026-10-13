
\set ON_ERROR_STOP on
\pset pager off

\echo '=============================================================='
\echo 'ETL-201Q STAGE C.2 - HISTORICAL TRANSACTION READINESS'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '=============================================================='

BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;
SET LOCAL statement_timeout = '900s';

\echo ''
\echo 'SECTION 1 - HISTORICAL EXTRACTION RESOLUTION'

WITH historical AS MATERIALIZED (
    SELECT
        r.load_batch_id,
        r.assistance_award_unique_key,
        r.assistance_transaction_unique_key,
        NULLIF(BTRIM(r.raw_record ->> 'cfda_number'), '')
            AS listing_code,
        NULLIF(BTRIM(r.raw_record ->> 'assistance_type_code'), '')
            AS type_code,
        NULLIF(
            BTRIM(r.raw_record ->> 'funding_opportunity_number'),
            ''
        ) AS opportunity_code
    FROM assistance.raw_award_transaction r
    WHERE r.load_batch_id IN (20, 21)
),
resolution AS MATERIALIZED (
    SELECT
        h.*,
        EXISTS (
            SELECT 1
            FROM assistance.award a
            WHERE a.assistance_award_unique_key =
                  h.assistance_award_unique_key
        ) AS award_resolved,
        EXISTS (
            SELECT 1
            FROM assistance.assistance_listing l
            WHERE l.cfda_number = h.listing_code
        ) AS listing_resolved,
        EXISTS (
            SELECT 1
            FROM assistance.assistance_type t
            WHERE t.assistance_type_code = h.type_code
        ) AS type_resolved,
        (
            h.opportunity_code IS NULL
            OR EXISTS (
                SELECT 1
                FROM assistance.funding_opportunity f
                WHERE f.funding_opportunity_number =
                      h.opportunity_code
            )
        ) AS opportunity_resolved
    FROM historical h
)
SELECT
    load_batch_id,
    COUNT(*) AS raw_observations,
    COUNT(*) FILTER (
        WHERE award_resolved
    ) AS award_resolved,
    COUNT(*) FILTER (
        WHERE NOT award_resolved
    ) AS award_unresolved,
    COUNT(*) FILTER (
        WHERE NOT listing_resolved
    ) AS listing_unresolved,
    COUNT(*) FILTER (
        WHERE NOT type_resolved
    ) AS type_unresolved,
    COUNT(*) FILTER (
        WHERE NOT opportunity_resolved
    ) AS opportunity_unresolved,
    COUNT(*) FILTER (
        WHERE award_resolved
          AND listing_resolved
          AND type_resolved
    ) AS loader_join_eligible,
    COUNT(*) FILTER (
        WHERE NOT (
            award_resolved
            AND listing_resolved
            AND type_resolved
        )
    ) AS loader_join_ineligible
FROM resolution
GROUP BY load_batch_id
ORDER BY load_batch_id;

\echo ''
\echo 'SECTION 2 - MISSING AWARD POPULATION'

WITH missing AS (
    SELECT
        r.assistance_award_unique_key,
        r.load_batch_id
    FROM assistance.raw_award_transaction r
    WHERE r.load_batch_id IN (20, 21)
      AND NOT EXISTS (
          SELECT 1
          FROM assistance.award a
          WHERE a.assistance_award_unique_key =
                r.assistance_award_unique_key
      )
)
SELECT
    COUNT(*) AS raw_observations,
    COUNT(DISTINCT assistance_award_unique_key)
        AS distinct_missing_award_keys,
    COUNT(*) FILTER (
        WHERE load_batch_id = 20
    ) AS batch_20_observations,
    COUNT(*) FILTER (
        WHERE load_batch_id = 21
    ) AS batch_21_observations
FROM missing;

\echo ''
\echo 'SECTION 3 - TRANSACTION KEY / AWARD KEY COLLISIONS'

WITH historical_pairs AS MATERIALIZED (
    SELECT DISTINCT
        assistance_transaction_unique_key,
        assistance_award_unique_key
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
),
collisions AS (
    SELECT
        assistance_transaction_unique_key,
        COUNT(*) AS distinct_award_keys
    FROM historical_pairs
    GROUP BY assistance_transaction_unique_key
    HAVING COUNT(*) > 1
)
SELECT
    COUNT(*) AS transaction_keys_with_multiple_awards,
    COALESCE(SUM(distinct_award_keys), 0)
        AS affected_transaction_award_pairs,
    COALESCE(MAX(distinct_award_keys), 0)
        AS maximum_awards_per_transaction_key
FROM collisions;

\echo ''
\echo 'SECTION 4 - REFERENCE CODE UNIQUENESS'

SELECT
    'assistance_listing' AS reference_table,
    COUNT(*) AS reference_rows,
    COUNT(DISTINCT cfda_number) AS distinct_codes,
    COUNT(*) FILTER (
        WHERE cfda_number IS NULL
    ) AS null_codes
FROM assistance.assistance_listing

UNION ALL

SELECT
    'assistance_type',
    COUNT(*),
    COUNT(DISTINCT assistance_type_code),
    COUNT(*) FILTER (
        WHERE assistance_type_code IS NULL
    )
FROM assistance.assistance_type

UNION ALL

SELECT
    'funding_opportunity',
    COUNT(*),
    COUNT(DISTINCT funding_opportunity_number),
    COUNT(*) FILTER (
        WHERE funding_opportunity_number IS NULL
    )
FROM assistance.funding_opportunity;

\echo ''
\echo 'SECTION 5 - HISTORICAL FISCAL YEAR PROFILE'

SELECT
    load_batch_id,
    raw_record ->> 'action_date_fiscal_year'
        AS reported_fiscal_year,
    COUNT(*) AS raw_observations
FROM assistance.raw_award_transaction
WHERE load_batch_id IN (20, 21)
GROUP BY
    load_batch_id,
    raw_record ->> 'action_date_fiscal_year'
ORDER BY
    load_batch_id,
    reported_fiscal_year;

ROLLBACK;

\echo ''
\echo 'ETL-201Q STAGE C.2 COMPLETE - READ ONLY'
