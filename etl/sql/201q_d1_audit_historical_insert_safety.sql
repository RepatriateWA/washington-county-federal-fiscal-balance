
\set ON_ERROR_STOP on
\pset pager off

\echo '=============================================================='
\echo 'ETL-201Q STAGE D.1 - HISTORICAL INSERT SAFETY'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '=============================================================='

BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;
SET LOCAL statement_timeout = '900s';

\echo ''
\echo 'SECTION 1 - CANONICAL TRANSACTION COVERAGE'

WITH eligible AS MATERIALIZED (
    SELECT
        r.load_batch_id,
        r.assistance_transaction_unique_key
    FROM assistance.raw_award_transaction r
    WHERE r.load_batch_id IN (20, 21)
      AND EXISTS (
          SELECT 1
          FROM assistance.award a
          WHERE a.assistance_award_unique_key =
                r.assistance_award_unique_key
      )
)
SELECT
    e.load_batch_id,
    COUNT(*) AS eligible_observations,
    COUNT(DISTINCT e.assistance_transaction_unique_key)
        AS distinct_keys,
    COUNT(*) FILTER (
        WHERE EXISTS (
            SELECT 1
            FROM assistance.award_transaction t
            WHERE t.assistance_transaction_unique_key =
                  e.assistance_transaction_unique_key
        )
    ) AS existing_canonical_matches
FROM eligible e
GROUP BY e.load_batch_id
ORDER BY e.load_batch_id;

\echo ''
\echo 'SECTION 2 - JOIN MULTIPLICITY'

WITH eligible AS MATERIALIZED (
    SELECT
        r.raw_assistance_transaction_id,
        r.assistance_award_unique_key,
        NULLIF(BTRIM(r.raw_record ->> 'cfda_number'), '')
            AS listing_code,
        NULLIF(
            BTRIM(r.raw_record ->> 'assistance_type_code'),
            ''
        ) AS type_code,
        NULLIF(
            BTRIM(r.raw_record ->> 'funding_opportunity_number'),
            ''
        ) AS opportunity_code
    FROM assistance.raw_award_transaction r
    WHERE r.load_batch_id IN (20, 21)
      AND EXISTS (
          SELECT 1
          FROM assistance.award a
          WHERE a.assistance_award_unique_key =
                r.assistance_award_unique_key
      )
),
joined AS (
    SELECT
        e.raw_assistance_transaction_id,
        COUNT(*) AS joined_rows
    FROM eligible e
    JOIN assistance.award a
      ON a.assistance_award_unique_key =
         e.assistance_award_unique_key
    JOIN assistance.assistance_listing l
      ON l.cfda_number = e.listing_code
    JOIN assistance.assistance_type t
      ON t.assistance_type_code = e.type_code
    LEFT JOIN assistance.funding_opportunity f
      ON f.funding_opportunity_number =
         e.opportunity_code
    GROUP BY e.raw_assistance_transaction_id
)
SELECT
    COUNT(*) AS observations_resolved,
    COUNT(*) FILTER (
        WHERE joined_rows <> 1
    ) AS observations_with_multiple_joins,
    COALESCE(SUM(joined_rows), 0) AS total_joined_rows
FROM joined;

\echo ''
\echo 'SECTION 3 - OBSERVATION LINK COVERAGE'

SELECT
    r.load_batch_id,
    COUNT(*) AS raw_observations,
    COUNT(o.raw_assistance_transaction_id)
        AS existing_observation_links
FROM assistance.raw_award_transaction r
LEFT JOIN assistance.award_transaction_observation o
  ON o.raw_assistance_transaction_id =
     r.raw_assistance_transaction_id
WHERE r.load_batch_id IN (20, 21)
GROUP BY r.load_batch_id
ORDER BY r.load_batch_id;

ROLLBACK;

\echo ''
\echo 'ETL-201Q STAGE D.1 COMPLETE - READ ONLY'
