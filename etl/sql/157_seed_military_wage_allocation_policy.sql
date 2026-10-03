-- ============================================================================
-- ETL-157 — Seed Federal Military Wage Allocation Policy
-- ============================================================================
--
-- Purpose
-- -------
-- Formally establish the WCFFBP source-selection and allocation policy for
-- federal military wages for FFY2015-FFY2024.
--
-- National accounting control:
--
--     OMB government-wide federal budget object-class obligations
--
--     Military wages =
--         Object Class 11.6
--       + Object Class 11.7
--
-- Geographic allocation evidence:
--
--     BEA SAINC7N
--     Line 2002 — Federal military wages
--
-- Washington allocation:
--
--     WA share =
--         BEA Washington military wages
--         / BEA United States military wages
--
--     WA ledger amount =
--         OMB national military wage obligation
--         * BEA Washington share
--
-- Validated implementation:
--
--     omb.v_federal_wage_obligation_control
--     bea.v_omb_military_wage_allocation
--
-- Important boundary:
--
--     OMB is the accounting source.
--     BEA is the geographic allocation source.
--
-- Direct BEA Washington military-wage dollars are retained as allocation and
-- reconciliation evidence and are NOT an additional federal inflow.
--
-- Temporal bridge:
--
--     BEA calendar-year share is applied to the matching federal fiscal year.
--
-- ============================================================================

BEGIN;


-- ============================================================================
-- Prevent accidental duplicate methodology seed
-- ============================================================================

DO $$
BEGIN

    IF EXISTS (
        SELECT 1
        FROM reference.federal_inflow_source_policy
        WHERE methodology_version = 'ANALYSIS-157-v1'
    ) THEN
        RAISE EXCEPTION
            'ANALYSIS-157-v1 already exists in reference.federal_inflow_source_policy.';
    END IF;

END
$$;


-- ============================================================================
-- Insert military wage source/allocation policy
-- ============================================================================

INSERT INTO reference.federal_inflow_source_policy (
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    source_selection_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
)
VALUES (
    'FEDERAL_WAGES',

    'MILITARY_WAGES',

    'FEDERAL_WAGE_OBLIGATIONS',

    'OMB_OBJECT_CLASS',

    'BEA_SAINC7N',

    ARRAY[
        'BEA_SAINC7N_DIRECT_WASHINGTON_DOLLARS'
    ]::text[],

    'INCLUDE_AFTER_RECONCILIATION',

    'For FFY2015-FFY2024, WCFFBP uses OMB government-wide federal budget '
    || 'object-class obligations as the national accounting control for '
    || 'military wages. Military wage obligations are defined as Object '
    || 'Class 11.6 plus Object Class 11.7. The preferred national accounting '
    || 'source is therefore OMB rather than the direct BEA military-wage '
    || 'dollar series. Geographic allocation to Washington State uses BEA '
    || 'SAINC7N line 2002 federal military wages. Washington''s allocation '
    || 'share is calculated as Washington BEA military wages divided by the '
    || 'BEA United States military-wage total, and that share is multiplied '
    || 'by the OMB national military-wage obligation control. The underlying '
    || 'BEA state-universe evidence preserves 60 geographies per year: the '
    || 'United States, 50 states, the District of Columbia, and eight BEA '
    || 'regions. For every year 2015-2024, the sum of the 50 states plus the '
    || 'District of Columbia reconciles exactly to the BEA United States row, '
    || 'and the eight BEA regional totals independently reconcile to that '
    || 'same United States value. Washington occurs exactly once per year. '
    || 'The allocation is implemented and validated in '
    || 'bea.v_omb_military_wage_allocation, which joins the BEA allocation '
    || 'shares to omb.v_federal_wage_obligation_control. The resulting '
    || 'Washington allocations independently reproduce the prior standalone '
    || 'diagnostic for all ten years. Direct BEA Washington military-wage '
    || 'dollar values are retained as geographic allocation and reconciliation '
    || 'evidence but are not added separately to the federal inflow ledger. '
    || 'The observed difference between direct BEA Washington values and '
    || 'OMB-scaled Washington allocations is treated as an accounting-scope '
    || 'difference and does not invalidate the geographic allocation weight. '
    || 'The temporal bridge explicitly applies the BEA calendar-year share '
    || 'for a given year to the matching OMB federal fiscal-year accounting '
    || 'control. This policy does not assert that BEA direct dollar values '
    || 'and OMB federal-budget obligations measure the same accounting '
    || 'universe. OMB determines the amount recognized in the federal fiscal '
    || 'ledger; BEA determines Washington''s geographic share.',

    'ANALYSIS-157-v1',

    2015,

    2024
);


-- ============================================================================
-- Validation
-- ============================================================================

DO $$
DECLARE
    v_policy_rows INTEGER;
    v_allocation_rows INTEGER;
    v_bad_years INTEGER;
    v_bad_reconciliation INTEGER;
    v_bad_allocation INTEGER;
BEGIN

    -- Policy must exist exactly once.

    SELECT COUNT(*)
    INTO v_policy_rows
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version = 'ANALYSIS-157-v1';


    IF v_policy_rows <> 1 THEN
        RAISE EXCEPTION
            'ETL-157 validation failed: expected exactly one ANALYSIS-157-v1 policy row; found %.',
            v_policy_rows;
    END IF;


    -- Validated implementation must contain all ten years.

    SELECT COUNT(*)
    INTO v_allocation_rows
    FROM bea.v_omb_military_wage_allocation
    WHERE fiscal_year BETWEEN 2015 AND 2024;


    IF v_allocation_rows <> 10 THEN
        RAISE EXCEPTION
            'ETL-157 validation failed: expected 10 validated military allocation rows; found %.',
            v_allocation_rows;
    END IF;


    -- Every year must be present exactly once.

    SELECT COUNT(*)
    INTO v_bad_years
    FROM (
        SELECT fiscal_year
        FROM bea.v_omb_military_wage_allocation
        WHERE fiscal_year BETWEEN 2015 AND 2024
        GROUP BY fiscal_year
        HAVING COUNT(*) <> 1
    ) AS bad;


    IF v_bad_years <> 0 THEN
        RAISE EXCEPTION
            'ETL-157 validation failed: % fiscal year(s) do not occur exactly once.',
            v_bad_years;
    END IF;


    -- Geographic denominator invariants must remain exact.

    SELECT COUNT(*)
    INTO v_bad_reconciliation
    FROM bea.v_omb_military_wage_allocation
    WHERE state_dc_reconciliation_difference_dollars <> 0
       OR region_reconciliation_difference_dollars <> 0
       OR state_dc_row_count <> 51
       OR region_row_count <> 8
       OR us_row_count <> 1
       OR wa_row_count <> 1;


    IF v_bad_reconciliation <> 0 THEN
        RAISE EXCEPTION
            'ETL-157 validation failed: % year(s) fail BEA geographic reconciliation.',
            v_bad_reconciliation;
    END IF;


    -- Ledger allocation must exist and be positive.

    SELECT COUNT(*)
    INTO v_bad_allocation
    FROM bea.v_omb_military_wage_allocation
    WHERE allocated_wa_military_wage_dollars IS NULL
       OR allocated_wa_military_wage_dollars <= 0;


    IF v_bad_allocation <> 0 THEN
        RAISE EXCEPTION
            'ETL-157 validation failed: % year(s) lack a valid Washington military wage allocation.',
            v_bad_allocation;
    END IF;


    RAISE NOTICE
        'ETL-157 validation PASSED: military wage source and allocation policy ANALYSIS-157-v1 established for FFY2015-FFY2024.';

END
$$;


COMMIT;