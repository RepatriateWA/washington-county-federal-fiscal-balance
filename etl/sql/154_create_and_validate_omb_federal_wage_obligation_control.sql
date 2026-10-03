-- ============================================================================
-- ETL-155 — Create and Validate OMB Federal Wage Obligation Control
-- ============================================================================
--
-- Purpose
-- -------
-- Derive the WCFFBP national federal wage-obligation controls directly from
-- the certified atomic OMB Object Class Analysis observations loaded by
-- ETL-154.
--
-- Source population
-- -----------------
-- omb.object_class_observation
--
-- Required object classes:
--
--   11.1  Full-time permanent
--   11.3  Other than full-time permanent
--   11.5  Other personnel compensation
--   11.6  Military personnel - basic allowance for housing
--   11.7  Military personnel
--   11.8  Special personal services payments
--
-- Derived accounting rules
-- ------------------------
--
--   MILITARY_WAGES
--       = 11.6 + 11.7
--
--   NONMILITARY_WAGES
--       = 11.1 + 11.3 + 11.5 + 11.8
--
--   TOTAL_WAGES
--       = MILITARY_WAGES + NONMILITARY_WAGES
--
-- Accounting measure:
--   OBLIGATIONS
--
-- Scope:
--   GOVERNMENT_WIDE
--
-- Coverage:
--   FFY2015-FFY2024
--
-- Methodological principle:
--   Derived controls must remain reproducible from atomic primary-source
--   observations. No derived total is stored as an unexplained base value.
-- ============================================================================

BEGIN;


-- ============================================================================
-- Derived view
-- ============================================================================

CREATE OR REPLACE VIEW omb.v_federal_wage_obligation_control AS

WITH latest_completed_batch AS (

    SELECT load_batch_id
    FROM omb.object_class_load_batch
    WHERE load_status = 'COMPLETED'
    ORDER BY load_batch_id DESC
    LIMIT 1
),

pivoted AS (

    SELECT
        o.target_fiscal_year,

        MAX(o.budget_vintage)
            AS budget_vintage,

        MAX(o.value_status)
            AS value_status,

        MAX(o.accounting_measure)
            AS accounting_measure,

        MAX(o.scope)
            AS scope,

        MAX(
            CASE
                WHEN o.object_class_code = '11.1'
                THEN o.obligation_dollars
            END
        ) AS oc_11_1_dollars,

        MAX(
            CASE
                WHEN o.object_class_code = '11.3'
                THEN o.obligation_dollars
            END
        ) AS oc_11_3_dollars,

        MAX(
            CASE
                WHEN o.object_class_code = '11.5'
                THEN o.obligation_dollars
            END
        ) AS oc_11_5_dollars,

        MAX(
            CASE
                WHEN o.object_class_code = '11.6'
                THEN o.obligation_dollars
            END
        ) AS oc_11_6_dollars,

        MAX(
            CASE
                WHEN o.object_class_code = '11.7'
                THEN o.obligation_dollars
            END
        ) AS oc_11_7_dollars,

        MAX(
            CASE
                WHEN o.object_class_code = '11.8'
                THEN o.obligation_dollars
            END
        ) AS oc_11_8_dollars

    FROM omb.object_class_observation o

    JOIN latest_completed_batch b
      ON b.load_batch_id = o.load_batch_id

    WHERE
        o.value_status = 'ACTUAL'
        AND o.scope = 'GOVERNMENT_WIDE'
        AND o.object_class_code IN (
            '11.1',
            '11.3',
            '11.5',
            '11.6',
            '11.7',
            '11.8'
        )

    GROUP BY
        o.target_fiscal_year
)

SELECT
    target_fiscal_year
        AS fiscal_year,

    budget_vintage,

    value_status,

    accounting_measure,

    scope,

    oc_11_1_dollars,

    oc_11_3_dollars,

    oc_11_5_dollars,

    oc_11_6_dollars,

    oc_11_7_dollars,

    oc_11_8_dollars,

    (
        oc_11_6_dollars
        + oc_11_7_dollars
    ) AS military_wage_obligations_dollars,

    (
        oc_11_1_dollars
        + oc_11_3_dollars
        + oc_11_5_dollars
        + oc_11_8_dollars
    ) AS nonmilitary_wage_obligations_dollars,

    (
        oc_11_1_dollars
        + oc_11_3_dollars
        + oc_11_5_dollars
        + oc_11_6_dollars
        + oc_11_7_dollars
        + oc_11_8_dollars
    ) AS total_wage_obligations_dollars

FROM pivoted;


-- ============================================================================
-- Validation output
-- ============================================================================

SELECT
    fiscal_year,

    ROUND(
        nonmilitary_wage_obligations_dollars
        / 1000000000.0,
        3
    ) AS nonmilitary_billions,

    ROUND(
        military_wage_obligations_dollars
        / 1000000000.0,
        3
    ) AS military_billions,

    ROUND(
        total_wage_obligations_dollars
        / 1000000000.0,
        3
    ) AS total_billions

FROM omb.v_federal_wage_obligation_control

ORDER BY fiscal_year;


-- ============================================================================
-- Hard validation
-- ============================================================================

DO $$
DECLARE
    row_count BIGINT;
    bad_null_count BIGINT;
    bad_year_count BIGINT;
    bad_semantic_count BIGINT;
    bad_expected_control_count BIGINT;
    fy2017_fy2018_difference_count BIGINT;
BEGIN

    -- ------------------------------------------------------------------------
    -- Exactly ten fiscal-year controls
    -- ------------------------------------------------------------------------

    SELECT COUNT(*)
    INTO row_count
    FROM omb.v_federal_wage_obligation_control;

    IF row_count <> 10 THEN
        RAISE EXCEPTION
            'Expected 10 OMB wage-control rows; found %.',
            row_count;
    END IF;


    -- ------------------------------------------------------------------------
    -- Exact FFY2015-FFY2024 coverage
    -- ------------------------------------------------------------------------

    SELECT COUNT(*)
    INTO bad_year_count
    FROM (
        SELECT fiscal_year
        FROM omb.v_federal_wage_obligation_control

        EXCEPT

        SELECT generate_series(
            2015,
            2024
        )::INTEGER
    ) x;

    IF bad_year_count <> 0 THEN
        RAISE EXCEPTION
            'OMB wage-control fiscal-year coverage is invalid.';
    END IF;


    -- ------------------------------------------------------------------------
    -- No missing atomic components
    -- ------------------------------------------------------------------------

    SELECT COUNT(*)
    INTO bad_null_count
    FROM omb.v_federal_wage_obligation_control
    WHERE
           oc_11_1_dollars IS NULL
        OR oc_11_3_dollars IS NULL
        OR oc_11_5_dollars IS NULL
        OR oc_11_6_dollars IS NULL
        OR oc_11_7_dollars IS NULL
        OR oc_11_8_dollars IS NULL;

    IF bad_null_count <> 0 THEN
        RAISE EXCEPTION
            'OMB wage-control view contains % rows with missing atomic values.',
            bad_null_count;
    END IF;


    -- ------------------------------------------------------------------------
    -- Semantic controls
    -- ------------------------------------------------------------------------

    SELECT COUNT(*)
    INTO bad_semantic_count
    FROM omb.v_federal_wage_obligation_control
    WHERE
           value_status IS DISTINCT FROM 'ACTUAL'
        OR accounting_measure
            IS DISTINCT FROM 'OBLIGATIONS_BY_OBJECT_CLASS'
        OR scope
            IS DISTINCT FROM 'GOVERNMENT_WIDE'
        OR budget_vintage
            IS DISTINCT FROM fiscal_year + 2;

    IF bad_semantic_count <> 0 THEN
        RAISE EXCEPTION
            'OMB wage-control semantic validation failed for % rows.',
            bad_semantic_count;
    END IF;


    -- ------------------------------------------------------------------------
    -- Hard expected-control validation
    --
    -- Values are dollars.
    -- These expected totals were independently derived outside PostgreSQL
    -- from the certified atomic OMB evidence population.
    -- ------------------------------------------------------------------------

    WITH expected AS (

        SELECT *
        FROM (
            VALUES
                (2015, 151722000000::BIGINT,  98258000000::BIGINT, 249980000000::BIGINT),
                (2016, 156145000000::BIGINT,  98238000000::BIGINT, 254383000000::BIGINT),
                (2017, 160144000000::BIGINT,  99471000000::BIGINT, 259615000000::BIGINT),
                (2018, 160144000000::BIGINT,  99471000000::BIGINT, 259615000000::BIGINT),
                (2019, 170536000000::BIGINT, 105899000000::BIGINT, 276435000000::BIGINT),
                (2020, 181373000000::BIGINT, 109572000000::BIGINT, 290945000000::BIGINT),
                (2021, 195549000000::BIGINT, 115002000000::BIGINT, 310551000000::BIGINT),
                (2022, 198465000000::BIGINT, 116550000000::BIGINT, 315015000000::BIGINT),
                (2023, 207461000000::BIGINT, 121022000000::BIGINT, 328483000000::BIGINT),
                (2024, 227393000000::BIGINT, 125047000000::BIGINT, 352440000000::BIGINT)
        ) AS t (
            fiscal_year,
            expected_nonmilitary,
            expected_military,
            expected_total
        )
    )

    SELECT COUNT(*)
    INTO bad_expected_control_count
    FROM expected e

    LEFT JOIN omb.v_federal_wage_obligation_control v
      ON v.fiscal_year = e.fiscal_year

    WHERE
           v.fiscal_year IS NULL

        OR v.nonmilitary_wage_obligations_dollars
            IS DISTINCT FROM e.expected_nonmilitary

        OR v.military_wage_obligations_dollars
            IS DISTINCT FROM e.expected_military

        OR v.total_wage_obligations_dollars
            IS DISTINCT FROM e.expected_total;


    IF bad_expected_control_count <> 0 THEN
        RAISE EXCEPTION
            'OMB derived-control validation failed for % fiscal years.',
            bad_expected_control_count;
    END IF;


    -- ------------------------------------------------------------------------
    -- Explicitly verify the manually confirmed FY2017/FY2018 duplicate
    -- published source condition.
    -- ------------------------------------------------------------------------

    WITH comparison AS (

        SELECT
            a.object_class_code,
            a.obligation_dollars AS fy2017_value,
            b.obligation_dollars AS fy2018_value

        FROM omb.object_class_observation a

        JOIN omb.object_class_observation b
          ON b.object_class_code = a.object_class_code

        WHERE
            a.target_fiscal_year = 2017
            AND b.target_fiscal_year = 2018
            AND a.value_status = 'ACTUAL'
            AND b.value_status = 'ACTUAL'
            AND a.scope = 'GOVERNMENT_WIDE'
            AND b.scope = 'GOVERNMENT_WIDE'
            AND a.object_class_code IN (
                '11.1',
                '11.3',
                '11.5',
                '11.6',
                '11.7',
                '11.8'
            )
    )

    SELECT COUNT(*)
    INTO fy2017_fy2018_difference_count
    FROM comparison
    WHERE fy2017_value
        IS DISTINCT FROM fy2018_value;


    IF fy2017_fy2018_difference_count <> 0 THEN
        RAISE EXCEPTION
            'Expected FY2017/FY2018 duplicate published source values are no longer preserved.';
    END IF;


    RAISE NOTICE
        'OMB federal wage-obligation validation PASSED: 10 fiscal years, FFY2015-FFY2024, exact derived controls, certified atomic source population.';

END
$$;


COMMIT;