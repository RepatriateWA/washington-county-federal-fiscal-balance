-- ============================================================================
-- ETL-156 — Create and Validate OMB/BEA Military Wage Allocation
-- ============================================================================
--
-- Purpose
-- -------
-- Allocate the OMB government-wide federal military wage obligation control
-- to Washington State using Washington's share of BEA SAINC7N military wages.
--
-- Accounting control:
--
--     OMB object classes 11.6 + 11.7
--     omb.v_federal_wage_obligation_control
--
-- Geographic allocation evidence:
--
--     BEA SAINC7N
--     Line 2002 — Federal military wages
--     bea.wage_observation
--
-- Formula:
--
--     WA allocation share
--         = BEA WA military wages
--           / BEA U.S. military wages
--
--     WA military wage obligation
--         = OMB national military wage obligations
--           * WA allocation share
--
-- Important methodological boundary
-- ---------------------------------
-- OMB remains the accounting source.
--
-- BEA SAINC7N supplies the geographic allocation weight.  The BEA Washington
-- dollar amount is retained as diagnostic evidence but is NOT substituted for
-- the OMB-derived federal fiscal ledger amount.
--
-- Temporal bridge
-- ---------------
-- Matching-year BEA calendar-year wage shares are applied to OMB federal
-- fiscal-year controls:
--
--     FFY 2015 <- BEA CY 2015 share
--     ...
--     FFY 2024 <- BEA CY 2024 share
--
-- This bridge is explicit in the output.
--
-- Geographic denominator invariant
-- --------------------------------
-- For every year:
--
--     sum(50 states + District of Columbia)
--         = BEA United States row
--
-- The eight BEA regional aggregates must independently sum to the same
-- United States value.
--
-- ============================================================================


BEGIN;


-- ============================================================================
-- Allocation view
-- ============================================================================

CREATE OR REPLACE VIEW bea.v_omb_military_wage_allocation AS

WITH latest_military_batch AS (

    SELECT MAX(load_batch_id) AS load_batch_id

    FROM bea.wage_load_batch

    WHERE status = 'COMPLETED'
      AND source_table = 'SAINC7N'
      AND source_line_code = '2002'
),

bea_year AS (

    SELECT
        w.load_batch_id,
        w.calendar_year,

        COUNT(*) AS geography_rows,

        COUNT(*) FILTER (
            WHERE w.geography_level = 'UNITED_STATES'
        ) AS us_row_count,

        COUNT(*) FILTER (
            WHERE w.geography_level IN (
                'STATE',
                'DISTRICT_OF_COLUMBIA'
            )
        ) AS state_dc_row_count,

        COUNT(*) FILTER (
            WHERE w.geography_level = 'BEA_REGION'
        ) AS region_row_count,

        COUNT(*) FILTER (
            WHERE w.source_geo_fips = '53000'
        ) AS wa_row_count,

        MAX(w.value_dollars) FILTER (
            WHERE w.geography_level = 'UNITED_STATES'
        ) AS bea_us_military_wages_dollars,

        MAX(w.value_dollars) FILTER (
            WHERE w.source_geo_fips = '53000'
        ) AS bea_wa_military_wages_dollars,

        SUM(w.value_dollars) FILTER (
            WHERE w.geography_level IN (
                'STATE',
                'DISTRICT_OF_COLUMBIA'
            )
        ) AS bea_state_dc_sum_dollars,

        SUM(w.value_dollars) FILTER (
            WHERE w.geography_level = 'BEA_REGION'
        ) AS bea_region_sum_dollars

    FROM bea.wage_observation AS w

    JOIN latest_military_batch AS b
      ON w.load_batch_id = b.load_batch_id

    WHERE w.wage_family = 'MILITARY'
      AND w.accounting_measure = 'WAGES_AND_SALARIES'
      AND w.reference_period_type = 'CALENDAR_YEAR'
      AND w.source_table = 'SAINC7N'
      AND w.source_line_code = '2002'

    GROUP BY
        w.load_batch_id,
        w.calendar_year
),

allocation AS (

    SELECT
        o.fiscal_year,

        b.calendar_year AS bea_calendar_year,

        b.load_batch_id AS bea_wage_load_batch_id,

        o.budget_vintage,

        o.value_status,

        o.accounting_measure AS omb_accounting_measure,

        o.scope AS omb_scope,

        o.military_wage_obligations_dollars
            AS omb_military_wage_control_dollars,

        b.bea_us_military_wages_dollars,

        b.bea_state_dc_sum_dollars,

        b.bea_region_sum_dollars,

        b.bea_wa_military_wages_dollars,

        b.geography_rows,

        b.us_row_count,

        b.state_dc_row_count,

        b.region_row_count,

        b.wa_row_count,

        (
            b.bea_state_dc_sum_dollars
            - b.bea_us_military_wages_dollars
        ) AS state_dc_reconciliation_difference_dollars,

        (
            b.bea_region_sum_dollars
            - b.bea_us_military_wages_dollars
        ) AS region_reconciliation_difference_dollars,

        (
            b.bea_wa_military_wages_dollars::numeric
            / NULLIF(
                b.bea_us_military_wages_dollars::numeric,
                0
            )
        ) AS bea_wa_share

    FROM omb.v_federal_wage_obligation_control AS o

    JOIN bea_year AS b
      ON b.calendar_year = o.fiscal_year

    WHERE o.fiscal_year BETWEEN 2015 AND 2024
)

SELECT
    fiscal_year,

    bea_calendar_year,

    bea_wage_load_batch_id,

    budget_vintage,

    value_status,

    omb_accounting_measure,

    omb_scope,

    omb_military_wage_control_dollars,

    bea_us_military_wages_dollars,

    bea_state_dc_sum_dollars,

    bea_region_sum_dollars,

    bea_wa_military_wages_dollars,

    bea_wa_share,

    ROUND(
        bea_wa_share * 100,
        6
    ) AS bea_wa_share_percent,

    ROUND(
        omb_military_wage_control_dollars::numeric
        * bea_wa_share,
        2
    ) AS allocated_wa_military_wage_dollars,

    ROUND(
        (
            omb_military_wage_control_dollars::numeric
            * bea_wa_share
        )
        - bea_wa_military_wages_dollars::numeric,
        2
    ) AS allocation_minus_bea_direct_dollars,

    ROUND(
        (
            omb_military_wage_control_dollars::numeric
            * bea_wa_share
        )
        / NULLIF(
            bea_wa_military_wages_dollars::numeric,
            0
        ),
        6
    ) AS allocation_to_bea_ratio,

    geography_rows,

    us_row_count,

    state_dc_row_count,

    region_row_count,

    wa_row_count,

    state_dc_reconciliation_difference_dollars,

    region_reconciliation_difference_dollars

FROM allocation;


COMMENT ON VIEW bea.v_omb_military_wage_allocation IS
'Allocates OMB government-wide military wage obligations to Washington using '
'Washington''s share of BEA SAINC7N line 2002 military wages. OMB is the '
'national accounting control; BEA supplies geographic allocation evidence. '
'Matching BEA calendar-year shares are applied to matching OMB federal '
'fiscal years.';


-- ============================================================================
-- Hard validation gates
-- ============================================================================

DO $$
DECLARE
    v_rows INTEGER;

    v_bad_years INTEGER;

    v_bad_structure INTEGER;

    v_bad_state_reconciliation INTEGER;

    v_bad_region_reconciliation INTEGER;

    v_bad_temporal_bridge INTEGER;

    v_bad_share INTEGER;

    v_bad_control INTEGER;

    v_min_year INTEGER;

    v_max_year INTEGER;

BEGIN

    -- ------------------------------------------------------------------------
    -- Exactly ten annual allocation rows
    -- ------------------------------------------------------------------------

    SELECT
        COUNT(*),
        MIN(fiscal_year),
        MAX(fiscal_year)
    INTO
        v_rows,
        v_min_year,
        v_max_year
    FROM bea.v_omb_military_wage_allocation;


    IF v_rows <> 10 THEN
        RAISE EXCEPTION
            'ETL-156 validation failed: expected 10 annual rows; found %.',
            v_rows;
    END IF;


    IF v_min_year <> 2015 OR v_max_year <> 2024 THEN
        RAISE EXCEPTION
            'ETL-156 validation failed: expected fiscal years 2015-2024; found %-%.',
            v_min_year,
            v_max_year;
    END IF;


    -- ------------------------------------------------------------------------
    -- Every year 2015-2024 must appear exactly once
    -- ------------------------------------------------------------------------

    SELECT COUNT(*)
    INTO v_bad_years
    FROM generate_series(
        2015,
        2024
    ) AS expected(fiscal_year)

    LEFT JOIN bea.v_omb_military_wage_allocation AS a
      ON a.fiscal_year = expected.fiscal_year

    WHERE a.fiscal_year IS NULL;


    IF v_bad_years <> 0 THEN
        RAISE EXCEPTION
            'ETL-156 validation failed: % expected fiscal years are missing.',
            v_bad_years;
    END IF;


    -- ------------------------------------------------------------------------
    -- BEA geography population must remain exactly:
    --
    -- 60 total
    --  1 United States
    -- 51 states + DC
    --  8 BEA regions
    --  1 Washington
    -- ------------------------------------------------------------------------

    SELECT COUNT(*)
    INTO v_bad_structure
    FROM bea.v_omb_military_wage_allocation

    WHERE geography_rows <> 60
       OR us_row_count <> 1
       OR state_dc_row_count <> 51
       OR region_row_count <> 8
       OR wa_row_count <> 1;


    IF v_bad_structure <> 0 THEN
        RAISE EXCEPTION
            'ETL-156 validation failed: % year(s) have invalid BEA geography structure.',
            v_bad_structure;
    END IF;


    -- ------------------------------------------------------------------------
    -- State/DC denominator must exactly equal BEA U.S.
    -- ------------------------------------------------------------------------

    SELECT COUNT(*)
    INTO v_bad_state_reconciliation
    FROM bea.v_omb_military_wage_allocation

    WHERE state_dc_reconciliation_difference_dollars <> 0;


    IF v_bad_state_reconciliation <> 0 THEN
        RAISE EXCEPTION
            'ETL-156 validation failed: states + DC do not reconcile to BEA U.S. for % year(s).',
            v_bad_state_reconciliation;
    END IF;


    -- ------------------------------------------------------------------------
    -- Eight BEA regions must independently equal BEA U.S.
    -- ------------------------------------------------------------------------

    SELECT COUNT(*)
    INTO v_bad_region_reconciliation
    FROM bea.v_omb_military_wage_allocation

    WHERE region_reconciliation_difference_dollars <> 0;


    IF v_bad_region_reconciliation <> 0 THEN
        RAISE EXCEPTION
            'ETL-156 validation failed: BEA regions do not reconcile to BEA U.S. for % year(s).',
            v_bad_region_reconciliation;
    END IF;


    -- ------------------------------------------------------------------------
    -- Explicit temporal bridge:
    -- matching CY allocation weight -> matching FFY accounting control
    -- ------------------------------------------------------------------------

    SELECT COUNT(*)
    INTO v_bad_temporal_bridge
    FROM bea.v_omb_military_wage_allocation

    WHERE fiscal_year <> bea_calendar_year;


    IF v_bad_temporal_bridge <> 0 THEN
        RAISE EXCEPTION
            'ETL-156 validation failed: % row(s) violate matching-year FFY/CY allocation bridge.',
            v_bad_temporal_bridge;
    END IF;


    -- ------------------------------------------------------------------------
    -- Allocation share must be economically possible
    -- ------------------------------------------------------------------------

    SELECT COUNT(*)
    INTO v_bad_share
    FROM bea.v_omb_military_wage_allocation

    WHERE bea_wa_share IS NULL
       OR bea_wa_share <= 0
       OR bea_wa_share >= 1;


    IF v_bad_share <> 0 THEN
        RAISE EXCEPTION
            'ETL-156 validation failed: % row(s) have invalid Washington allocation shares.',
            v_bad_share;
    END IF;


    -- ------------------------------------------------------------------------
    -- OMB control must be present and positive
    -- ------------------------------------------------------------------------

    SELECT COUNT(*)
    INTO v_bad_control
    FROM bea.v_omb_military_wage_allocation

    WHERE omb_military_wage_control_dollars IS NULL
       OR omb_military_wage_control_dollars <= 0;


    IF v_bad_control <> 0 THEN
        RAISE EXCEPTION
            'ETL-156 validation failed: % row(s) lack a valid OMB military wage control.',
            v_bad_control;
    END IF;


    RAISE NOTICE
        'ETL-156 validation PASSED: 10 years, OMB accounting controls joined to BEA SAINC7N military allocation evidence.';

    RAISE NOTICE
        'BEA geography validation PASSED: 60 rows/year; states + DC = U.S.; regions = U.S.; Washington exactly once/year.';

END
$$;


COMMIT;