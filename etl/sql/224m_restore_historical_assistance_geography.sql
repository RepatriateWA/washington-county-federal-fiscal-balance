
-- =====================================================================
-- ETL-224M
-- Restore FY2018-FY2019 Washington assistance performance geography
--
-- Scope: load_batch_id IN (20, 21)
-- Expected canonical transactions: 207343
-- County-specific: 199786
-- Washington state-only: 7557
--
-- Only assistance.award_transaction.place_of_performance_id changes.
-- =====================================================================

BEGIN;

DO $$
DECLARE
    v_targets BIGINT;
    v_raw_matches BIGINT;
    v_county_matches BIGINT;
    v_state_only BIGINT;
    v_invalid BIGINT;
    v_updated BIGINT;
    v_remaining BIGINT;
BEGIN

    -- Confirm state-only fallback identity.
    IF NOT EXISTS (
        SELECT 1
        FROM procurement.place
        WHERE place_id = 1
          AND state_fips = '53'
          AND county_fips IS NULL
          AND city_name IS NULL
          AND zip4 IS NULL
          AND place_source_condition = 'WASHINGTON_UNSPECIFIED'
    ) THEN
        RAISE EXCEPTION
            'ETL-224M: Washington state-only place identity invalid';
    END IF;

    -- Ensure county-only mapping is unique.
    IF EXISTS (
        SELECT 1
        FROM procurement.place
        WHERE state_fips = '53'
          AND county_fips ~ '^53[0-9]{3}$'
          AND city_name IS NULL
          AND zip4 IS NULL
        GROUP BY county_fips
        HAVING COUNT(*) <> 1
    ) THEN
        RAISE EXCEPTION
            'ETL-224M: Ambiguous county-only place mapping';
    END IF;

    -- Reconfirm the target population and raw geography.
    WITH county_places AS MATERIALIZED (
        SELECT county_fips, MIN(place_id) AS place_id
        FROM procurement.place
        WHERE state_fips = '53'
          AND county_fips ~ '^53[0-9]{3}$'
          AND city_name IS NULL
          AND zip4 IS NULL
        GROUP BY county_fips
    ),
    targets AS MATERIALIZED (
        SELECT
            t.load_batch_id,
            t.source_row_number,
            r.source_row_number AS raw_match,
            NULLIF(BTRIM(r.raw_record ->>
                'prime_award_transaction_place_of_performance_state_fips_code'), '')
                AS state_fips,
            NULLIF(BTRIM(r.raw_record ->>
                'prime_award_transaction_place_of_performance_county_fips_code'), '')
                AS county_fips
        FROM assistance.award_transaction t
        LEFT JOIN assistance.raw_award_transaction r
          ON r.load_batch_id = t.load_batch_id
         AND r.source_row_number = t.source_row_number
        WHERE t.load_batch_id IN (20, 21)
          AND t.place_of_performance_id IS NULL
    )

    SELECT
        COUNT(*),
        COUNT(*) FILTER (
            WHERE x.raw_match IS NOT NULL
        ),
        COUNT(*) FILTER (
            WHERE x.county_fips ~ '^53[0-9]{3}$'
              AND cp.place_id IS NOT NULL
        ),
        COUNT(*) FILTER (
            WHERE x.county_fips IS NULL
              AND x.state_fips = '53'
        ),
        COUNT(*) FILTER (
            WHERE x.raw_match IS NULL
               OR x.state_fips IS DISTINCT FROM '53'
               OR (
                   x.county_fips IS NOT NULL
                   AND (
                       x.county_fips !~ '^53[0-9]{3}$'
                       OR cp.place_id IS NULL
                   )
               )
        )
    INTO
        v_targets,
        v_raw_matches,
        v_county_matches,
        v_state_only,
        v_invalid
    FROM targets x
    LEFT JOIN county_places cp
      ON cp.county_fips = x.county_fips;

    IF v_targets <> 207343
       OR v_raw_matches <> 207343
       OR v_county_matches <> 199786
       OR v_state_only <> 7557
       OR v_invalid <> 0
    THEN
        RAISE EXCEPTION
            'ETL-224M preflight failed: targets %, raw %, county %, state-only %, invalid %',
            v_targets, v_raw_matches, v_county_matches,
            v_state_only, v_invalid;
    END IF;

    RAISE NOTICE
        'ETL-224M preflight PASS: % county, % state-only',
        v_county_matches, v_state_only;

    -- Assign existing county-only places, or state-only place_id 1.
    WITH county_places AS MATERIALIZED (
        SELECT county_fips, MIN(place_id) AS place_id
        FROM procurement.place
        WHERE state_fips = '53'
          AND county_fips ~ '^53[0-9]{3}$'
          AND city_name IS NULL
          AND zip4 IS NULL
        GROUP BY county_fips
    ),
    assignments AS MATERIALIZED (
        SELECT
            t.load_batch_id,
            t.source_row_number,
            COALESCE(cp.place_id, 1) AS target_place_id
        FROM assistance.award_transaction t
        JOIN assistance.raw_award_transaction r
          ON r.load_batch_id = t.load_batch_id
         AND r.source_row_number = t.source_row_number
        LEFT JOIN county_places cp
          ON cp.county_fips = NULLIF(BTRIM(r.raw_record ->>
              'prime_award_transaction_place_of_performance_county_fips_code'), '')
        WHERE t.load_batch_id IN (20, 21)
          AND t.place_of_performance_id IS NULL
    )
    UPDATE assistance.award_transaction t
    SET place_of_performance_id = a.target_place_id
    FROM assignments a
    WHERE t.load_batch_id = a.load_batch_id
      AND t.source_row_number = a.source_row_number
      AND t.place_of_performance_id IS NULL;

    GET DIAGNOSTICS v_updated = ROW_COUNT;

    IF v_updated <> 207343 THEN
        RAISE EXCEPTION
            'ETL-224M updated % rows; expected 207343',
            v_updated;
    END IF;

    SELECT COUNT(*)
    INTO v_remaining
    FROM assistance.award_transaction
    WHERE load_batch_id IN (20, 21)
      AND place_of_performance_id IS NULL;

    IF v_remaining <> 0 THEN
        RAISE EXCEPTION
            'ETL-224M remaining unlinked transactions: %',
            v_remaining;
    END IF;

    RAISE NOTICE
        'ETL-224M PASS: % transaction geography links restored',
        v_updated;

END $$;

COMMIT;
