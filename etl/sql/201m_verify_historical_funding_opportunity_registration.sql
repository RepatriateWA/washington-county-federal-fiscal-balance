
\set ON_ERROR_STOP on
\pset pager off

BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;
SET LOCAL statement_timeout = '300s';

\echo ''
\echo '============================================================'
\echo 'ETL-201M v0.1 - POST-REGISTRATION VERIFICATION'
\echo 'FY2018 batch 20 / FY2019 batch 21'
\echo 'READ ONLY'
\echo '============================================================'

\echo ''
\echo 'SECTION 1 - COMMITTED REFERENCE POPULATION'

SELECT
    COUNT(*) AS reference_rows,
    COUNT(DISTINCT funding_opportunity_number)
        AS distinct_reference_numbers,
    COUNT(*) FILTER (
        WHERE funding_opportunity_goals_text IS NULL
    ) AS null_goals_text_count
FROM assistance.funding_opportunity;

\echo ''
\echo 'SECTION 2 - HISTORICAL COHORT PROTECTION'

WITH historical AS MATERIALIZED (
    SELECT
        assistance_award_unique_key AS award_key,
        NULLIF(
            BTRIM(raw_record ->> 'cfda_number'), ''
        ) AS listing_code,
        NULLIF(
            BTRIM(raw_record ->> 'assistance_type_code'), ''
        ) AS type_code
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
),
grouped AS (
    SELECT
        award_key,
        COUNT(DISTINCT listing_code) AS listing_count,
        COUNT(DISTINCT type_code) AS type_count
    FROM historical
    GROUP BY award_key
)
SELECT
    COUNT(*) AS historical_awards,
    COUNT(*) FILTER (
        WHERE a.assistance_award_unique_key IS NOT NULL
    ) AS existing_canonical,
    COUNT(*) FILTER (
        WHERE a.assistance_award_unique_key IS NULL
          AND g.listing_count <= 1
          AND g.type_count <= 1
    ) AS missing_nonconflicted,
    COUNT(*) FILTER (
        WHERE a.assistance_award_unique_key IS NULL
          AND (
              g.listing_count > 1
              OR g.type_count > 1
          )
    ) AS missing_conflicted
FROM grouped AS g
LEFT JOIN assistance.award AS a
  ON a.assistance_award_unique_key = g.award_key;

\echo ''
\echo 'SECTION 3 - HISTORICAL OPPORTUNITY RESOLUTION'

WITH historical AS MATERIALIZED (
    SELECT
        assistance_award_unique_key AS award_key,
        load_batch_id,
        source_row_number,
        NULLIF(
            BTRIM(raw_record ->> 'cfda_number'), ''
        ) AS listing_code,
        NULLIF(
            BTRIM(raw_record ->> 'assistance_type_code'), ''
        ) AS type_code,
        NULLIF(
            BTRIM(
                raw_record ->> 'funding_opportunity_number'
            ), ''
        ) AS opportunity_code
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
),
eligible AS MATERIALIZED (
    SELECT h.award_key
    FROM historical AS h
    LEFT JOIN assistance.award AS a
      ON a.assistance_award_unique_key = h.award_key
    WHERE a.assistance_award_unique_key IS NULL
    GROUP BY h.award_key
    HAVING COUNT(DISTINCT h.listing_code) <= 1
       AND COUNT(DISTINCT h.type_code) <= 1
),
candidate_rows AS (
    SELECT h.*
    FROM historical AS h
    JOIN eligible AS e ON e.award_key = h.award_key
)
SELECT
    COUNT(*) AS candidate_source_rows,
    COUNT(DISTINCT c.award_key) AS candidate_awards,
    COUNT(*) FILTER (
        WHERE c.opportunity_code IS NOT NULL
    ) AS populated_opportunity_rows,
    COUNT(*) FILTER (
        WHERE c.opportunity_code IS NOT NULL
          AND f.funding_opportunity_id IS NULL
    ) AS unresolved_opportunity_rows,
    COUNT(DISTINCT c.opportunity_code) FILTER (
        WHERE c.opportunity_code IS NOT NULL
          AND f.funding_opportunity_id IS NULL
    ) AS unresolved_opportunity_codes
FROM candidate_rows AS c
LEFT JOIN assistance.funding_opportunity AS f
  ON f.funding_opportunity_number = c.opportunity_code;

\echo ''
\echo 'SECTION 4 - CONTROL ASSERTIONS'

DO $verify$
DECLARE
    v_references bigint;
    v_null_goals bigint;
    v_existing bigint;
    v_candidates bigint;
    v_conflicted bigint;
BEGIN
    SELECT COUNT(*),
           COUNT(*) FILTER (
               WHERE funding_opportunity_goals_text IS NULL
           )
    INTO v_references, v_null_goals
    FROM assistance.funding_opportunity;

    IF v_references <> 3117 OR v_null_goals <> 178 THEN
        RAISE EXCEPTION
            'Reference population mismatch: rows %, null goals %',
            v_references, v_null_goals;
    END IF;

    WITH historical AS (
        SELECT
            assistance_award_unique_key AS award_key,
            COUNT(DISTINCT NULLIF(
                BTRIM(raw_record ->> 'cfda_number'), ''
            )) AS listings,
            COUNT(DISTINCT NULLIF(
                BTRIM(raw_record ->> 'assistance_type_code'), ''
            )) AS types
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
              AND h.listings <= 1 AND h.types <= 1
        ),
        COUNT(*) FILTER (
            WHERE a.assistance_award_unique_key IS NULL
              AND (h.listings > 1 OR h.types > 1)
        )
    INTO v_existing, v_candidates, v_conflicted
    FROM historical AS h
    LEFT JOIN assistance.award AS a
      ON a.assistance_award_unique_key = h.award_key;

    IF v_existing <> 10219
       OR v_candidates <> 156401
       OR v_conflicted <> 90
    THEN
        RAISE EXCEPTION
            'Historical cohort changed: existing %, candidates %, held %',
            v_existing, v_candidates, v_conflicted;
    END IF;

    RAISE NOTICE 'ETL-201M COHORT AND REFERENCE ASSERTIONS: PASS';
END;
$verify$;

ROLLBACK;

\echo ''
\echo 'ETL-201M COMPLETE - READ ONLY'
