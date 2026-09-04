-- ============================================================================
-- ETL-158 — Seed Federal Civilian Wage Allocation Policy
-- ============================================================================
--
-- Purpose
-- -------
-- Formally establish the WCFFBP source-selection and allocation policy for
-- federal civilian wages for FFY2015-FFY2024.
--
-- National accounting control:
--
--     OMB government-wide federal budget object-class obligations
--
--     Civilian / nonmilitary wages =
--         Object Class 11.1
--       + Object Class 11.3
--       + Object Class 11.5
--       + Object Class 11.8
--
-- Geographic allocation evidence:
--
--     OPM FedScope
--     Non-Seasonal Full-Time Permanent personnel
--
-- Rockefeller Institute methodology evidence indicates that civilian federal
-- wages were geographically allocated using OPM salary-by-state information
-- for non-seasonal full-time personnel. Civilian Federal Budget wages exclude
-- U.S. Postal Service wages.
--
-- Important boundary:
--
--     OMB is the accounting source.
--     OPM is the geographic allocation source.
--
-- Direct OPM or BEA Washington civilian-wage dollar values are retained as
-- allocation and reconciliation evidence and are NOT an additional federal
-- inflow when an OMB-controlled allocation is used.
--
-- Public FedScope limitation:
--
--     OPM location represents official duty station rather than residence.
--
--     Public FedScope contains suppressed-location observations and, beginning
--     materially in FFY2017, substantial suppression of exact SALARY values.
--
--     WCFFBP does not invent state assignments or exact salary values for
--     suppressed observations.
--
--     Any Washington allocations reconstructed from the public FedScope
--     archive are WCFFBP estimates and must not be represented as published
--     Rockefeller Institute Washington values.
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
        WHERE methodology_version = 'ANALYSIS-158-v1'
    ) THEN
        RAISE EXCEPTION
            'ANALYSIS-158-v1 already exists in reference.federal_inflow_source_policy.';
    END IF;

END
$$;


-- ============================================================================
-- Insert civilian wage source/allocation policy
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

    'CIVILIAN_WAGES',

    'FEDERAL_WAGE_OBLIGATIONS',

    'OMB_OBJECT_CLASS',

    'OPM_FEDSCOPE',

    ARRAY[
        'OPM_FEDSCOPE_DIRECT_WASHINGTON_DOLLARS',
        'BEA_SAINC7N_DIRECT_WASHINGTON_DOLLARS'
    ]::text[],

    'INCLUDE_AFTER_RECONCILIATION',

    'For FFY2015-FFY2024, WCFFBP uses OMB government-wide federal budget '
    || 'object-class obligations as the national accounting control for '
    || 'civilian federal wages. Civilian/nonmilitary wage obligations are '
    || 'defined as Object Class 11.1 plus Object Class 11.3 plus Object '
    || 'Class 11.5 plus Object Class 11.8. The preferred national accounting '
    || 'source is therefore OMB rather than direct OPM or BEA civilian-wage '
    || 'dollar values. Geographic allocation to Washington State follows the '
    || 'Rockefeller Institute methodological architecture using OPM FedScope '
    || 'salary information for non-seasonal full-time personnel. Rockefeller '
    || 'documentation identifies OPM salary-by-state files as the civilian '
    || 'wage allocation evidence for FFY2015 and FFY2016. Civilian Federal '
    || 'Budget wages exclude U.S. Postal Service wages. OPM location represents '
    || 'official duty station rather than employee residence. The preserved '
    || 'public FedScope archive shows material disclosure limitations: '
    || 'suppressed-location observations are present throughout the series, '
    || 'and beginning materially in FFY2017 a large population also lacks '
    || 'exact SALARY values. WCFFBP does not invent geographic assignments '
    || 'or exact salary values for those suppressed observations. Any '
    || 'Washington civilian-wage allocations reconstructed from public '
    || 'FedScope data are therefore WCFFBP estimates and are not represented '
    || 'as published Rockefeller Institute Washington values. The FFY2015 '
    || 'and FFY2016 public FedScope snapshots contain substantially more '
    || 'complete exact salary information than later years, but suppressed '
    || 'geography remains a limitation. For FFY2017-FFY2024, public FedScope '
    || 'salary suppression materially limits exact reconstruction of the '
    || 'Rockefeller state-allocation weights. Direct OPM Washington salary '
    || 'values and direct BEA SAINC7N civilian-wage dollar values are retained '
    || 'as geographic, diagnostic, and reconciliation evidence but are not '
    || 'added separately to the federal inflow ledger when an OMB-controlled '
    || 'allocation is used. OMB determines the amount recognized in the '
    || 'federal fiscal ledger; OPM provides the best available geographic '
    || 'allocation evidence subject to the documented suppression limitations.',

    'ANALYSIS-158-v1',

    2015,

    2024
);


-- ============================================================================
-- Validation
-- ============================================================================

DO $$
DECLARE
    v_policy_rows INTEGER;
    v_omb_rows INTEGER;
    v_bad_omb_years INTEGER;
    v_bad_controls INTEGER;
BEGIN

    -- Policy must exist exactly once.

    SELECT COUNT(*)
    INTO v_policy_rows
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version = 'ANALYSIS-158-v1';


    IF v_policy_rows <> 1 THEN
        RAISE EXCEPTION
            'ETL-158 validation failed: expected exactly one ANALYSIS-158-v1 policy row; found %.',
            v_policy_rows;
    END IF;


    -- OMB national civilian-wage control must contain all ten years.

    SELECT COUNT(*)
    INTO v_omb_rows
    FROM omb.v_federal_wage_obligation_control
    WHERE fiscal_year BETWEEN 2015 AND 2024;


    IF v_omb_rows <> 10 THEN
        RAISE EXCEPTION
            'ETL-158 validation failed: expected 10 OMB wage-control rows; found %.',
            v_omb_rows;
    END IF;


    -- Every year must be present exactly once.

    SELECT COUNT(*)
    INTO v_bad_omb_years
    FROM (
        SELECT fiscal_year
        FROM omb.v_federal_wage_obligation_control
        WHERE fiscal_year BETWEEN 2015 AND 2024
        GROUP BY fiscal_year
        HAVING COUNT(*) <> 1
    ) AS bad;


    IF v_bad_omb_years <> 0 THEN
        RAISE EXCEPTION
            'ETL-158 validation failed: % OMB fiscal year(s) do not occur exactly once.',
            v_bad_omb_years;
    END IF;


    -- Civilian/nonmilitary national control must exist and be positive.

    SELECT COUNT(*)
    INTO v_bad_controls
    FROM omb.v_federal_wage_obligation_control
    WHERE fiscal_year BETWEEN 2015 AND 2024
      AND (
            nonmilitary_wage_obligations_dollars IS NULL
         OR nonmilitary_wage_obligations_dollars <= 0
      );


    IF v_bad_controls <> 0 THEN
        RAISE EXCEPTION
            'ETL-158 validation failed: % year(s) lack a valid OMB civilian/nonmilitary wage control.',
            v_bad_controls;
    END IF;


    RAISE NOTICE
        'ETL-158 validation PASSED: civilian wage source and allocation policy ANALYSIS-158-v1 established for FFY2015-FFY2024.';

END
$$;


COMMIT;