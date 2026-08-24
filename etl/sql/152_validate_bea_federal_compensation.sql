-- ============================================================================
-- ETL-152 — Validate BEA Federal Compensation
-- ============================================================================
--
-- Purpose
-- -------
-- Validate the initial BEA federal civilian and military compensation load.
--
-- Required controls:
--
--   1. Exactly one completed load batch is validated here.
--
--   2. Expected observation counts:
--
--          820 total
--          780 county
--           40 state
--
--   3. For each compensation family and calendar year 2015-2024:
--
--          sum(39 CAINC6N county observations)
--              =
--          CAINC6N Washington state aggregate
--              =
--          SAINC6N Washington state control
--
--   4. County coverage must equal all 39 Washington counties for every
--      family-year combination.
--
--   5. Source semantics must remain:
--
--          reference_period_type = CALENDAR_YEAR
--          geographic_basis      = PLACE_OF_WORK
--          accounting_measure    = COMPENSATION_OF_EMPLOYEES
--
-- Methodological status
-- --------------------
-- SOURCE / ACCOUNTING VALIDATION.
--
-- This validation does not yet make BEA compensation additive to the common
-- federal-inflow ledger. Source-overlap policy remains a later step.
-- ============================================================================


-- ============================================================================
-- 1. Latest completed load batch
-- ============================================================================

WITH latest_batch AS (

    SELECT load_batch_id
    FROM bea.compensation_load_batch
    WHERE status = 'COMPLETED'
    ORDER BY load_batch_id DESC
    LIMIT 1
)

SELECT
    b.load_batch_id,
    b.dataset_name,
    b.status,
    b.rows_loaded,
    b.calendar_year_start,
    b.calendar_year_end,
    b.acquisition_manifest_path,
    b.acquisition_manifest_sha256,
    b.source_retrieved_utc,
    b.created_at,
    b.completed_at

FROM bea.compensation_load_batch b

JOIN latest_batch lb
  ON lb.load_batch_id = b.load_batch_id;


-- ============================================================================
-- 2. Observation-count controls
-- ============================================================================

WITH latest_batch AS (

    SELECT load_batch_id
    FROM bea.compensation_load_batch
    WHERE status = 'COMPLETED'
    ORDER BY load_batch_id DESC
    LIMIT 1
)

SELECT
    COUNT(*) AS total_observations,

    COUNT(*) FILTER (
        WHERE geography_level = 'COUNTY'
    ) AS county_observations,

    COUNT(*) FILTER (
        WHERE geography_level = 'STATE'
    ) AS state_observations,

    COUNT(DISTINCT county_id) FILTER (
        WHERE geography_level = 'COUNTY'
    ) AS distinct_counties,

    COUNT(DISTINCT calendar_year)
        AS distinct_years,

    COUNT(DISTINCT compensation_family)
        AS distinct_compensation_families

FROM bea.compensation_observation o

JOIN latest_batch lb
  ON lb.load_batch_id = o.load_batch_id;


-- ============================================================================
-- 3. Source-series controls
-- ============================================================================

WITH latest_batch AS (

    SELECT load_batch_id
    FROM bea.compensation_load_batch
    WHERE status = 'COMPLETED'
    ORDER BY load_batch_id DESC
    LIMIT 1
)

SELECT
    compensation_family,
    source_table,
    source_line_code,
    geography_level,
    COUNT(*) AS observation_count,
    MIN(calendar_year) AS min_calendar_year,
    MAX(calendar_year) AS max_calendar_year

FROM bea.compensation_observation o

JOIN latest_batch lb
  ON lb.load_batch_id = o.load_batch_id

GROUP BY
    compensation_family,
    source_table,
    source_line_code,
    geography_level

ORDER BY
    compensation_family,
    source_table,
    geography_level;


-- ============================================================================
-- 4. Semantic controls
-- ============================================================================

WITH latest_batch AS (

    SELECT load_batch_id
    FROM bea.compensation_load_batch
    WHERE status = 'COMPLETED'
    ORDER BY load_batch_id DESC
    LIMIT 1
)

SELECT
    reference_period_type,
    geographic_basis,
    accounting_measure,
    source_unit,
    source_unit_multiplier,
    COUNT(*) AS observation_count

FROM bea.compensation_observation o

JOIN latest_batch lb
  ON lb.load_batch_id = o.load_batch_id

GROUP BY
    reference_period_type,
    geographic_basis,
    accounting_measure,
    source_unit,
    source_unit_multiplier

ORDER BY 1, 2, 3, 4, 5;


-- ============================================================================
-- 5. County coverage by family/year
-- ============================================================================

WITH latest_batch AS (

    SELECT load_batch_id
    FROM bea.compensation_load_batch
    WHERE status = 'COMPLETED'
    ORDER BY load_batch_id DESC
    LIMIT 1
)

SELECT
    compensation_family,
    calendar_year,
    COUNT(*) AS county_observation_count,
    COUNT(DISTINCT county_id) AS distinct_county_count

FROM bea.compensation_observation o

JOIN latest_batch lb
  ON lb.load_batch_id = o.load_batch_id

WHERE
    geography_level = 'COUNTY'
    AND source_table = 'CAINC6N'

GROUP BY
    compensation_family,
    calendar_year

ORDER BY
    compensation_family,
    calendar_year;


-- ============================================================================
-- 6. Three-way annual reconciliation
-- ============================================================================

WITH latest_batch AS (

    SELECT load_batch_id
    FROM bea.compensation_load_batch
    WHERE status = 'COMPLETED'
    ORDER BY load_batch_id DESC
    LIMIT 1
),

county_sum AS (

    SELECT
        compensation_family,
        calendar_year,
        SUM(value_dollars) AS county_sum_dollars

    FROM bea.compensation_observation o

    JOIN latest_batch lb
      ON lb.load_batch_id = o.load_batch_id

    WHERE
        source_table = 'CAINC6N'
        AND geography_level = 'COUNTY'

    GROUP BY
        compensation_family,
        calendar_year
),

cainc_state AS (

    SELECT
        compensation_family,
        calendar_year,
        value_dollars AS cainc_state_dollars

    FROM bea.compensation_observation o

    JOIN latest_batch lb
      ON lb.load_batch_id = o.load_batch_id

    WHERE
        source_table = 'CAINC6N'
        AND geography_level = 'STATE'
),

sainc_state AS (

    SELECT
        compensation_family,
        calendar_year,
        value_dollars AS sainc_state_dollars

    FROM bea.compensation_observation o

    JOIN latest_batch lb
      ON lb.load_batch_id = o.load_batch_id

    WHERE
        source_table = 'SAINC6N'
        AND geography_level = 'STATE'
)

SELECT
    c.compensation_family,
    c.calendar_year,

    c.county_sum_dollars,

    ca.cainc_state_dollars,

    sa.sainc_state_dollars,

    c.county_sum_dollars
        - ca.cainc_state_dollars
        AS county_vs_cainc_difference,

    ca.cainc_state_dollars
        - sa.sainc_state_dollars
        AS cainc_vs_sainc_difference,

    c.county_sum_dollars
        - sa.sainc_state_dollars
        AS county_vs_sainc_difference

FROM county_sum c

JOIN cainc_state ca
  ON ca.compensation_family = c.compensation_family
 AND ca.calendar_year = c.calendar_year

JOIN sainc_state sa
  ON sa.compensation_family = c.compensation_family
 AND sa.calendar_year = c.calendar_year

ORDER BY
    c.compensation_family,
    c.calendar_year;


-- ============================================================================
-- 7. Hard validation
-- ============================================================================

DO $$
DECLARE
    latest_batch_id BIGINT;

    total_observation_count BIGINT;
    county_observation_count BIGINT;
    state_observation_count BIGINT;

    bad_county_coverage_count BIGINT;
    bad_reconciliation_count BIGINT;
    bad_semantic_count BIGINT;

BEGIN

    SELECT load_batch_id
    INTO latest_batch_id
    FROM bea.compensation_load_batch
    WHERE status = 'COMPLETED'
    ORDER BY load_batch_id DESC
    LIMIT 1;


    IF latest_batch_id IS NULL THEN
        RAISE EXCEPTION
            'No completed BEA compensation load batch found.';
    END IF;


    -- ------------------------------------------------------------------------
    -- Count controls
    -- ------------------------------------------------------------------------

    SELECT
        COUNT(*),

        COUNT(*) FILTER (
            WHERE geography_level = 'COUNTY'
        ),

        COUNT(*) FILTER (
            WHERE geography_level = 'STATE'
        )

    INTO
        total_observation_count,
        county_observation_count,
        state_observation_count

    FROM bea.compensation_observation

    WHERE load_batch_id = latest_batch_id;


    IF total_observation_count <> 820 THEN
        RAISE EXCEPTION
            'Expected 820 BEA compensation observations; found %.',
            total_observation_count;
    END IF;


    IF county_observation_count <> 780 THEN
        RAISE EXCEPTION
            'Expected 780 BEA county observations; found %.',
            county_observation_count;
    END IF;


    IF state_observation_count <> 40 THEN
        RAISE EXCEPTION
            'Expected 40 BEA state observations; found %.',
            state_observation_count;
    END IF;


    -- ------------------------------------------------------------------------
    -- County coverage controls
    -- ------------------------------------------------------------------------

    SELECT COUNT(*)
    INTO bad_county_coverage_count
    FROM (

        SELECT
            compensation_family,
            calendar_year

        FROM bea.compensation_observation

        WHERE
            load_batch_id = latest_batch_id
            AND source_table = 'CAINC6N'
            AND geography_level = 'COUNTY'

        GROUP BY
            compensation_family,
            calendar_year

        HAVING
            COUNT(*) <> 39
            OR COUNT(DISTINCT county_id) <> 39

    ) bad;


    IF bad_county_coverage_count <> 0 THEN
        RAISE EXCEPTION
            'BEA county coverage validation failed for % family-year groups.',
            bad_county_coverage_count;
    END IF;


    -- ------------------------------------------------------------------------
    -- Semantic controls
    -- ------------------------------------------------------------------------

    SELECT COUNT(*)
    INTO bad_semantic_count

    FROM bea.compensation_observation

    WHERE
        load_batch_id = latest_batch_id
        AND (
               reference_period_type
                    IS DISTINCT FROM 'CALENDAR_YEAR'

            OR geographic_basis
                    IS DISTINCT FROM 'PLACE_OF_WORK'

            OR accounting_measure
                    IS DISTINCT FROM 'COMPENSATION_OF_EMPLOYEES'

            OR source_unit
                    IS DISTINCT FROM 'Thousands of dollars'

            OR source_unit_multiplier
                    IS DISTINCT FROM 3
        );


    IF bad_semantic_count <> 0 THEN
        RAISE EXCEPTION
            'BEA semantic validation failed for % observations.',
            bad_semantic_count;
    END IF;


    -- ------------------------------------------------------------------------
    -- Three-way reconciliation
    -- ------------------------------------------------------------------------

    WITH county_sum AS (

        SELECT
            compensation_family,
            calendar_year,
            SUM(value_dollars) AS county_sum_dollars

        FROM bea.compensation_observation

        WHERE
            load_batch_id = latest_batch_id
            AND source_table = 'CAINC6N'
            AND geography_level = 'COUNTY'

        GROUP BY
            compensation_family,
            calendar_year
    ),

    cainc_state AS (

        SELECT
            compensation_family,
            calendar_year,
            value_dollars AS cainc_state_dollars

        FROM bea.compensation_observation

        WHERE
            load_batch_id = latest_batch_id
            AND source_table = 'CAINC6N'
            AND geography_level = 'STATE'
    ),

    sainc_state AS (

        SELECT
            compensation_family,
            calendar_year,
            value_dollars AS sainc_state_dollars

        FROM bea.compensation_observation

        WHERE
            load_batch_id = latest_batch_id
            AND source_table = 'SAINC6N'
            AND geography_level = 'STATE'
    )

    SELECT COUNT(*)
    INTO bad_reconciliation_count

    FROM county_sum c

    JOIN cainc_state ca
      ON ca.compensation_family = c.compensation_family
     AND ca.calendar_year = c.calendar_year

    JOIN sainc_state sa
      ON sa.compensation_family = c.compensation_family
     AND sa.calendar_year = c.calendar_year

    WHERE
           c.county_sum_dollars
                IS DISTINCT FROM ca.cainc_state_dollars

        OR ca.cainc_state_dollars
                IS DISTINCT FROM sa.sainc_state_dollars

        OR c.county_sum_dollars
                IS DISTINCT FROM sa.sainc_state_dollars;


    IF bad_reconciliation_count <> 0 THEN
        RAISE EXCEPTION
            'BEA compensation reconciliation failed for % family-year groups.',
            bad_reconciliation_count;
    END IF;


    RAISE NOTICE
        'BEA compensation validation PASSED for load_batch_id=%: 820 observations, 39 counties, 2015-2024, exact three-way reconciliation.',
        latest_batch_id;

END
$$;