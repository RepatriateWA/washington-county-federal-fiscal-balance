-- ============================================================================
-- ETL-135 — Seed OASDI Federal Inflow Source Policy
-- ============================================================================
--
-- Purpose
-- -------
-- Establish the first empirically supported federal-inflow overlap policy.
--
-- Evidence established before this migration:
--
--   * SSA benefit_payments contains county-level OASDI benefit measures.
--   * SSA benefit_type = 'Total' reconciles to the sum of the detailed
--     retirement, survivors, and disability categories subject only to
--     trivial source rounding.
--   * USAspending Assistance Listings:
--
--         96.001  Social Security Disability Insurance
--         96.002  Social Security Retirement Insurance
--         96.004  Social Security Survivors Insurance
--
--     materially overlap the SSA OASDI benefit universe.
--
--   * USAspending and SSA values are similar but not identical and therefore
--     must NOT be mechanically added or subtracted from one another.
--
-- Policy
-- ------
-- SSA is the preferred accounting source and county allocation source for
-- OASDI for the empirically reconciled 2020-2024 period.
--
-- USAspending observations remain fully preserved but do not create a second
-- additive accounting path for these same OASDI benefit families.
--
-- SSI / Assistance Listing 96.006 is explicitly OUTSIDE this policy.
-- ============================================================================

BEGIN;


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

SELECT
    'SOCIAL_SECURITY',
    'OASDI',

    'ANNUAL_BENEFIT_PAYMENTS',

    'SSA',
    'SSA',
    ARRAY[
        'USASPENDING_ASSISTANCE'
    ]::TEXT[],

    'INCLUDE_AFTER_RECONCILIATION',

    (
        'SSA benefit_payments is the preferred accounting and county-allocation '
        || 'source for Old-Age, Survivors, and Disability Insurance (OASDI). '
        || 'SSA benefit_type = Total is additive for the statewide OASDI '
        || 'accounting measure; detailed SSA benefit types are analytical '
        || 'components and must not be added again to Total. '
        || 'USAspending Assistance Listings 96.001, 96.002, and 96.004 are '
        || 'overlapping representations of disability, retirement, and '
        || 'survivors insurance respectively. Those USAspending observations '
        || 'remain preserved for provenance and reconciliation but do not '
        || 'contribute an additional additive OASDI amount when the SSA measure '
        || 'is used. Assistance Listing 96.006 Supplemental Security Income '
        || '(SSI) is not covered by this policy. '
        || 'Empirical comparison for 2020-2024 showed USAspending OASDI below '
        || 'SSA OASDI by approximately 2.98% to 10.47%, demonstrating material '
        || 'overlap without numerical identity.'
    ),

    'ANALYSIS-116-v1',

    2020,
    2024

WHERE NOT EXISTS (
    SELECT 1
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'SOCIAL_SECURITY'
      AND inflow_subfamily = 'OASDI'
      AND accounting_measure = 'ANNUAL_BENEFIT_PAYMENTS'
      AND methodology_version = 'ANALYSIS-116-v1'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024
);


-- ============================================================================
-- Validation
-- ============================================================================

DO $$
DECLARE
    policy_count BIGINT;
    preferred_source_value TEXT;
    treatment_value TEXT;
BEGIN

    SELECT
        COUNT(*),
        MAX(preferred_source),
        MAX(ledger_treatment)
    INTO
        policy_count,
        preferred_source_value,
        treatment_value
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'SOCIAL_SECURITY'
      AND inflow_subfamily = 'OASDI'
      AND accounting_measure = 'ANNUAL_BENEFIT_PAYMENTS'
      AND methodology_version = 'ANALYSIS-116-v1'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;


    IF policy_count <> 1 THEN
        RAISE EXCEPTION
            'Expected exactly one OASDI source-policy row; found %.',
            policy_count;
    END IF;


    IF preferred_source_value IS DISTINCT FROM 'SSA' THEN
        RAISE EXCEPTION
            'OASDI preferred source is %, expected SSA.',
            preferred_source_value;
    END IF;


    IF treatment_value IS DISTINCT FROM
        'INCLUDE_AFTER_RECONCILIATION'
    THEN
        RAISE EXCEPTION
            'OASDI ledger treatment is %, expected INCLUDE_AFTER_RECONCILIATION.',
            treatment_value;
    END IF;

END
$$;


COMMIT;