-- ============================================================================
-- ETL-149 — Seed VA GDX / USAspending Procurement Federal Inflow Source Policy
-- ============================================================================
--
-- Purpose
-- -------
-- Establish the empirically supported federal-inflow overlap policy governing
-- Department of Veterans Affairs (VA) expenditures represented by:
--
--     * VA Geographic Distribution of VA Expenditures (GDX), and
--     * USAspending procurement obligations.
--
-- This policy is initially limited to FY2024, the bridge year used for the
-- detailed reconciliation because revised GDX separates Direct and Indirect
-- expenditures and provides the strongest available source-scope evidence.
--
--
-- Evidence established before this migration
-- -------------------------------------------
--
-- 1. VA GDX FY2020-FY2024 was loaded and validated.
--
-- 2. FY2024 VA GDX provides the authoritative candidate expenditure control
--    for Washington:
--
--        approximately $6.927 billion total VA expenditures.
--
-- 3. The canonical FY2024 Washington USAspending VA procurement population
--    was independently reproduced as:
--
--        2,319 transactions
--        $384,771,014.98 net federal_action_obligation
--
--    using:
--
--        fiscal_year = 2024
--        Washington USAspending place of performance
--        Department of Veterans Affairs funding agency
--
-- 4. USAspending procurement federal_action_obligation is an OBLIGATION
--    measure, not an annual-expenditure measure.
--
--    Query 141 demonstrated:
--
--        $337.831M  award performance overlapping FY2024
--         $76.606M  award performance beginning after FY2024
--        -$32.263M  negative modifications / deobligations
--          $2.596M  award-period mismatch transactions
--
-- 5. The Tahoma National Cemetery Phase 3 contract provides a decisive
--    obligation-versus-expenditure timing example:
--
--        FY2024 action date:        2024-09-27
--        FY2024 obligation:         $73,086,136
--        performance start:         2024-10-31
--        performance end:           2027-05-15
--
--    Thus a major FY2024 USAspending obligation represents a multi-year
--    contractual commitment whose performance begins after FY2024.
--
-- 6. Query 143 classified $322.261M, approximately 83.75% of the FY2024
--    procurement obligation control, with HIGH substantive confidence into
--    activity families corresponding to major GDX expenditure families:
--
--        Medical Care
--        Construction
--        Memorial Benefits
--
--    This establishes strong source-scope overlap but does NOT establish
--    transaction-level or same-fiscal-year numerical identity.
--
-- 7. Queries 144-145 showed that the remaining procurement population
--    includes administrative support, enterprise telecommunications,
--    Veteran transportation, social-support services, facility operations,
--    and mixed-purpose procurement. PSC classification alone is therefore
--    insufficient to establish accounting treatment.
--
-- 8. Queries 146-148 established that USAspending Washington place of
--    performance is not equivalent to Washington-only VA expenditure
--    attribution.
--
--    Query 148 conservatively classified the FY2024 procurement control as:
--
--        $152.088M  confirmed Washington-local
--         $10.927M  confirmed enterprise or multistate
--         $12.589M  confirmed non-Washington beneficiary/facility
--        $209.167M  unresolved geographic attribution
--
--    All underlying USAspending records remain preserved.
--
-- 9. Authoritative VA GDX methodology defines GDX as an expenditure measure
--    and includes major VA institutional expenditure families implicated by
--    procurement, including Medical Care, Construction, Memorial Benefits,
--    supplies, infrastructure, prosthetics, research, and related activity.
--
--
-- Policy
-- ------
--
-- VA GDX is the preferred accounting source and allocation source for the
-- FY2024 VA annual-expenditure measure.
--
-- USAspending procurement is a subordinate reconciliation/provenance source.
-- USAspending procurement obligations must NOT be mechanically added to GDX
-- expenditures.
--
-- All USAspending procurement records remain preserved for:
--
--     provenance,
--     transaction-level analysis,
--     source reconciliation,
--     geographic diagnostics,
--     and identification of possible GDX scope exceptions.
--
-- A USAspending procurement class may create a separately additive accounting
-- path ONLY where affirmative evidence establishes that the corresponding
-- expenditure activity is outside the GDX expenditure universe.
--
-- IMPORTANT QUALIFICATION:
--
-- This policy does NOT assert that the full $384,771,014.98 FY2024
-- USAspending procurement obligation total appears dollar-for-dollar inside
-- the FY2024 GDX total.
--
-- It establishes instead that:
--
--     * USAspending procurement is obligation-based;
--     * GDX is expenditure-based;
--     * the sources materially overlap in substantive scope;
--     * the sources use non-identical timing and geographic attribution;
--     * therefore the procurement stream is NON-ADDITIVE when GDX is used
--       as the authoritative VA expenditure measure.
--
-- Evidence trail:
--     ETL / analysis queries 136-148
--     notes/reconcile_va_notes.md
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
    'VETERANS_AFFAIRS',
    'TOTAL_VA_EXPENDITURES',

    'ANNUAL_EXPENDITURES',

    'VA_GDX',
    'VA_GDX',
    ARRAY[
        'USASPENDING_PROCUREMENT'
    ]::TEXT[],

    'INCLUDE_AFTER_RECONCILIATION',

    (
        'VA Geographic Distribution of VA Expenditures (GDX) is the '
        || 'preferred accounting and allocation source for FY2024 VA annual '
        || 'expenditures. USAspending procurement is retained as a '
        || 'transaction-level provenance and reconciliation source but does '
        || 'not create a second additive accounting path when GDX is used. '

        || 'The canonical FY2024 Washington USAspending VA procurement '
        || 'population contains 2,319 transactions and $384,771,014.98 of '
        || 'net federal_action_obligation. federal_action_obligation is an '
        || 'obligation measure and is not equivalent to fiscal-year '
        || 'expenditure. The FY2024 Tahoma National Cemetery Phase 3 award '
        || 'illustrates the timing difference: $73,086,136 was obligated on '
        || '2024-09-27 for performance beginning 2024-10-31 and extending '
        || 'through 2027-05-15. '

        || 'Detailed FY2024 reconciliation classified approximately '
        || '$322.261 million, or 83.75 percent of the procurement obligation '
        || 'control, with high substantive confidence into Medical Care, '
        || 'Construction, or Memorial Benefits candidate activity families '
        || 'that correspond to major GDX expenditure families. This '
        || 'establishes material scope overlap but does not imply '
        || 'transaction-level or same-year dollar identity. '

        || 'Geographic review also demonstrated that USAspending Washington '
        || 'place of performance is not equivalent to Washington-only VA '
        || 'expenditure attribution. The FY2024 population includes '
        || 'Washington-local activity, enterprise or multistate procurement, '
        || 'and transactions explicitly benefiting non-Washington VA '
        || 'facilities. '

        || 'Accordingly, USAspending VA procurement obligations must not be '
        || 'mechanically added to VA GDX expenditures. All USAspending '
        || 'procurement observations remain preserved for provenance, '
        || 'reconciliation, transaction analysis, and identification of '
        || 'possible GDX scope exceptions. A procurement class may be '
        || 'included separately only where affirmative evidence establishes '
        || 'that the corresponding expenditure activity lies outside the '
        || 'GDX expenditure universe. '

        || 'This policy does not assert that the full $384,771,014.98 '
        || 'USAspending FY2024 procurement obligation total is contained '
        || 'dollar-for-dollar within FY2024 GDX. It establishes that '
        || 'obligation and expenditure measures with materially overlapping '
        || 'scope, different timing, and different geographic attribution '
        || 'must not be treated as independent additive federal inflows.'
    ),

    'ANALYSIS-149-v1',

    2024,
    2024

WHERE NOT EXISTS (
    SELECT 1
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'VETERANS_AFFAIRS'
      AND inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
      AND accounting_measure = 'ANNUAL_EXPENDITURES'
      AND methodology_version = 'ANALYSIS-149-v1'
      AND valid_from_fiscal_year = 2024
      AND valid_through_fiscal_year = 2024
);


-- ============================================================================
-- Validation
-- ============================================================================

DO $$
DECLARE
    policy_count BIGINT;
    preferred_source_value TEXT;
    allocation_source_value TEXT;
    treatment_value TEXT;
    overlapping_sources_value TEXT[];
BEGIN

    SELECT
        COUNT(*),
        MAX(preferred_source),
        MAX(allocation_source),
        MAX(ledger_treatment),
        MAX(overlapping_sources)
    INTO
        policy_count,
        preferred_source_value,
        allocation_source_value,
        treatment_value,
        overlapping_sources_value
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'VETERANS_AFFAIRS'
      AND inflow_subfamily = 'TOTAL_VA_EXPENDITURES'
      AND accounting_measure = 'ANNUAL_EXPENDITURES'
      AND methodology_version = 'ANALYSIS-149-v1'
      AND valid_from_fiscal_year = 2024
      AND valid_through_fiscal_year = 2024;


    IF policy_count <> 1 THEN
        RAISE EXCEPTION
            'Expected exactly one FY2024 VA GDX source-policy row; found %.',
            policy_count;
    END IF;


    IF preferred_source_value IS DISTINCT FROM 'VA_GDX' THEN
        RAISE EXCEPTION
            'VA preferred source is %, expected VA_GDX.',
            preferred_source_value;
    END IF;


    IF allocation_source_value IS DISTINCT FROM 'VA_GDX' THEN
        RAISE EXCEPTION
            'VA allocation source is %, expected VA_GDX.',
            allocation_source_value;
    END IF;


    IF treatment_value IS DISTINCT FROM
        'INCLUDE_AFTER_RECONCILIATION'
    THEN
        RAISE EXCEPTION
            'VA ledger treatment is %, expected INCLUDE_AFTER_RECONCILIATION.',
            treatment_value;
    END IF;


    IF overlapping_sources_value IS DISTINCT FROM
        ARRAY['USASPENDING_PROCUREMENT']::TEXT[]
    THEN
        RAISE EXCEPTION
            'VA overlapping_sources is %, expected {USASPENDING_PROCUREMENT}.',
            overlapping_sources_value;
    END IF;

END
$$;


COMMIT;