
\set ON_ERROR_STOP on
\pset pager off

\echo ''
\echo '======================================================================'
\echo 'ETL-201L STAGE B v0.1'
\echo 'CONTROLLED HISTORICAL FUNDING-OPPORTUNITY REGISTRATION'
\echo 'FY2018 batch 20 / FY2019 batch 21'
\echo 'REFERENCE-ONLY WRITE - NO CANONICAL AWARD OR LEDGER CHANGES'
\echo '======================================================================'

BEGIN;

SET TRANSACTION ISOLATION LEVEL SERIALIZABLE, READ WRITE;
SET LOCAL statement_timeout = '300s';
SET LOCAL lock_timeout = '30s';

-- Protect the reference population against concurrent modifications.
-- SHARE ROW EXCLUSIVE permits reads while preventing concurrent writes.
LOCK TABLE assistance.funding_opportunity
    IN SHARE ROW EXCLUSIVE MODE;

\echo ''
\echo 'SECTION 1 - BASELINE REFERENCE POPULATION'

SELECT
    COUNT(*) AS existing_reference_rows,
    COUNT(DISTINCT funding_opportunity_number)
        AS distinct_reference_numbers
FROM assistance.funding_opportunity;

\echo ''
\echo 'SECTION 2 - CONTROLLED REGISTRATION'

DO $etl_201l$
DECLARE
    v_baseline_count       bigint;
    v_candidate_awards     bigint;
    v_missing_codes       bigint;
    v_affected_rows       bigint;
    v_affected_awards     bigint;
    v_source_identities   bigint;
    v_inserted            bigint;
    v_final_count         bigint;
    v_remaining_codes     bigint;
    v_remaining_rows      bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_baseline_count
    FROM assistance.funding_opportunity;

    IF v_baseline_count <> 3097 THEN
        RAISE EXCEPTION
            'Baseline mismatch: expected 3097, found %',
            v_baseline_count;
    END IF;

    -- Materialize the exact eligible historical population
    -- within this transaction.
    WITH historical AS MATERIALIZED (
        SELECT
            raw.assistance_award_unique_key AS award_key,
            raw.load_batch_id,
            raw.source_row_number,
            NULLIF(
                BTRIM(raw.raw_record ->> 'cfda_number'), ''
            ) AS listing_code,
            NULLIF(
                BTRIM(
                    raw.raw_record ->> 'assistance_type_code'
                ), ''
            ) AS type_code,
            NULLIF(
                BTRIM(
                    raw.raw_record ->> 'funding_opportunity_number'
                ), ''
            ) AS opportunity_code
        FROM assistance.raw_award_transaction AS raw
        WHERE raw.load_batch_id IN (20, 21)
    ),
    grouped AS MATERIALIZED (
        SELECT
            award_key,
            COUNT(DISTINCT listing_code) AS listing_count,
            COUNT(DISTINCT type_code) AS type_count
        FROM historical
        GROUP BY award_key
    ),
    eligible AS MATERIALIZED (
        SELECT g.award_key
        FROM grouped AS g
        LEFT JOIN assistance.award AS a
          ON a.assistance_award_unique_key = g.award_key
        WHERE a.assistance_award_unique_key IS NULL
          AND g.listing_count <= 1
          AND g.type_count <= 1
    ),
    candidate_rows AS MATERIALIZED (
        SELECT h.*
        FROM historical AS h
        JOIN eligible AS e
          ON e.award_key = h.award_key
    ),
    unresolved AS MATERIALIZED (
        SELECT c.*
        FROM candidate_rows AS c
        WHERE c.opportunity_code IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM assistance.funding_opportunity AS f
              WHERE f.funding_opportunity_number =
                    c.opportunity_code
          )
    )
    SELECT
        (SELECT COUNT(*) FROM eligible),
        (SELECT COUNT(DISTINCT opportunity_code)
         FROM unresolved),
        (SELECT COUNT(*) FROM unresolved),
        (SELECT COUNT(DISTINCT award_key)
         FROM unresolved),
        (SELECT COUNT(DISTINCT (
            load_batch_id, source_row_number
         )) FROM unresolved)
    INTO
        v_candidate_awards,
        v_missing_codes,
        v_affected_rows,
        v_affected_awards,
        v_source_identities;

    RAISE NOTICE
        'Candidate awards: %', v_candidate_awards;
    RAISE NOTICE
        'Missing codes: %', v_missing_codes;
    RAISE NOTICE
        'Affected observations: %', v_affected_rows;
    RAISE NOTICE
        'Affected awards: %', v_affected_awards;
    RAISE NOTICE
        'Distinct source identities: %', v_source_identities;

    IF v_candidate_awards <> 156401
       OR v_missing_codes <> 20
       OR v_affected_rows <> 56
       OR v_affected_awards <> 41
       OR v_source_identities <> 56
    THEN
        RAISE EXCEPTION
            'Pre-insertion historical controls failed';
    END IF;

    -- Register only source-observed identifiers.
    -- No descriptive goals text is manufactured.
    WITH historical AS MATERIALIZED (
        SELECT
            raw.assistance_award_unique_key AS award_key,
            NULLIF(
                BTRIM(raw.raw_record ->> 'cfda_number'), ''
            ) AS listing_code,
            NULLIF(
                BTRIM(
                    raw.raw_record ->> 'assistance_type_code'
                ), ''
            ) AS type_code,
            NULLIF(
                BTRIM(
                    raw.raw_record ->> 'funding_opportunity_number'
                ), ''
            ) AS opportunity_code
        FROM assistance.raw_award_transaction AS raw
        WHERE raw.load_batch_id IN (20, 21)
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
    proposed AS MATERIALIZED (
        SELECT DISTINCT h.opportunity_code
        FROM historical AS h
        JOIN eligible AS e
          ON e.award_key = h.award_key
        WHERE h.opportunity_code IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM assistance.funding_opportunity AS f
              WHERE f.funding_opportunity_number =
                    h.opportunity_code
          )
    ),
    inserted AS (
        INSERT INTO assistance.funding_opportunity (
            funding_opportunity_number,
            funding_opportunity_goals_text
        )
        SELECT
            opportunity_code,
            NULL::text
        FROM proposed
        ORDER BY opportunity_code
        ON CONFLICT (funding_opportunity_number)
        DO NOTHING
        RETURNING funding_opportunity_id
    )
    SELECT COUNT(*)
    INTO v_inserted
    FROM inserted;

    RAISE NOTICE 'Inserted reference records: %', v_inserted;

    IF v_inserted <> 20 THEN
        RAISE EXCEPTION
            'Insertion count mismatch: expected 20, found %',
            v_inserted;
    END IF;

    SELECT COUNT(*)
    INTO v_final_count
    FROM assistance.funding_opportunity;

    IF v_final_count <> 3117 THEN
        RAISE EXCEPTION
            'Final reference count mismatch: expected 3117, found %',
            v_final_count;
    END IF;

    -- Verify that no candidate source opportunity code
    -- remains unresolved after registration.
    WITH historical AS MATERIALIZED (
        SELECT
            assistance_award_unique_key AS award_key,
            NULLIF(
                BTRIM(raw_record ->> 'cfda_number'), ''
            ) AS listing_code,
            NULLIF(
                BTRIM(
                    raw_record ->> 'assistance_type_code'
                ), ''
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
    unresolved AS (
        SELECT h.opportunity_code
        FROM historical AS h
        JOIN eligible AS e
          ON e.award_key = h.award_key
        WHERE h.opportunity_code IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM assistance.funding_opportunity AS f
              WHERE f.funding_opportunity_number =
                    h.opportunity_code
          )
    )
    SELECT
        COUNT(DISTINCT opportunity_code),
        COUNT(*)
    INTO
        v_remaining_codes,
        v_remaining_rows
    FROM unresolved;

    IF v_remaining_codes <> 0
       OR v_remaining_rows <> 0
    THEN
        RAISE EXCEPTION
            'Post-insertion unresolved opportunities: codes %, rows %',
            v_remaining_codes,
            v_remaining_rows;
    END IF;

    RAISE NOTICE
        'FINAL REFERENCE POPULATION: %', v_final_count;
    RAISE NOTICE
        'REMAINING UNRESOLVED CODES: %', v_remaining_codes;
    RAISE NOTICE
        'ETL-201L STAGE B VALIDATION: PASS';
END;
$etl_201l$;

\echo ''
\echo 'SECTION 3 - FINAL REFERENCE POPULATION'

SELECT
    COUNT(*) AS reference_rows,
    COUNT(DISTINCT funding_opportunity_number)
        AS distinct_reference_numbers,
    COUNT(*) FILTER (
        WHERE funding_opportunity_goals_text IS NULL
    ) AS null_goals_text_count
FROM assistance.funding_opportunity;

COMMIT;

\echo ''
\echo 'ETL-201L STAGE B COMPLETE - TRANSACTION COMMITTED'
