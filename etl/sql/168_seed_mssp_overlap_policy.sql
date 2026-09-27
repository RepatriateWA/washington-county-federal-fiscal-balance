-- ETL-168
-- Seed Medicare Shared Savings Program (MSSP) EarnSaveLoss overlap policy
-- and close the MSSP additive-accounting reconciliation branch.
--
-- Evidence basis:
--   * CMS MSSP Washington organizational-connection bridge v0.1
--   * CMS MSSP assigned-beneficiary-by-county source certification v0.4
--   * CMS MSSP 2019 regular/off-cycle source certification v0.5.1
--   * CMS MSSP 2016-2018 historical source certification v0.6
--   * CMS MSSP county value-semantics certification v0.7
--   * CMS MSSP geographic suppression constraints v0.8
--   * CMS MSSP geographic beneficiary bounds v0.9
--   * CMS MSSP auxiliary-estimator feasibility v1.0
--   * CMS MSSP EarnSaveLoss geographic allocation sensitivity v1.1
--   * CMS MSSP accounting/additivity reconciliation v1.2
--   * Official CMS Medicare Shared Savings Program documentation
--   * Medicare Trustees Trust Fund accounting documentation
--
-- Policy:
--   * MSSP EarnSaveLoss is a Medicare financial-settlement measure.
--   * Earned shared-savings payments are Medicare Trust Fund outflows;
--     shared-loss recoveries are Medicare Trust Fund receipts.
--   * Where WCFFBP uses CMS-native Medicare Trust Fund expenditure
--     accounting as its principal Medicare accounting path, EarnSaveLoss
--     is not an additional additive federal inflow path.
--   * MSSP performance and geographic data are retained as
--     reconciliation/provenance evidence.
--   * Certified MSSP geographic analysis does not authorize a second
--     plus sign in the principal Medicare ledger.
--   * 2015 geographic allocation remains NOT ESTIMATED because the
--     original county-level source artifact was not recovered.
--   * 2016 geographic evidence remains subject to the certified
--     UNRESOLVED_HISTORICAL_ENCODING caveat.
--   * 2019 regular and 2019A off-cycle participation periods remain
--     distinct observations in MSSP analytical evidence.
--
-- This migration changes policy metadata only. It does not alter CMS source
-- observations, MSSP financial results, geographic bounds, modeled sensitivity
-- scenarios, Medicare Trust Fund controls, or county allocations.

BEGIN;

-- Fail closed if the established policy table does not have the architecture
-- expected from ETL-135 / ETL-149 / ETL-157 / ETL-158 / ETL-167.
DO $$
DECLARE
    missing_columns TEXT;
BEGIN
    SELECT string_agg(required.column_name, ', ' ORDER BY required.column_name)
      INTO missing_columns
    FROM (
        VALUES
            ('inflow_family'),
            ('inflow_subfamily'),
            ('accounting_measure'),
            ('preferred_source'),
            ('allocation_source'),
            ('overlapping_sources'),
            ('ledger_treatment'),
            ('source_selection_basis'),
            ('methodology_version'),
            ('valid_from_fiscal_year'),
            ('valid_through_fiscal_year')
    ) AS required(column_name)
    WHERE NOT EXISTS (
        SELECT 1
        FROM information_schema.columns c
        WHERE c.table_schema = 'reference'
          AND c.table_name = 'federal_inflow_source_policy'
          AND c.column_name = required.column_name
    );

    IF missing_columns IS NOT NULL THEN
        RAISE EXCEPTION
            'ETL-168 expected reference.federal_inflow_source_policy columns are missing: %',
            missing_columns;
    END IF;
END
$$;

-- The established ledger_treatment vocabulary does not include a literal
-- OVERLAPPING value. EXCLUDE_DUPLICATE is therefore the fail-closed ledger
-- treatment: preserve MSSP EarnSaveLoss as Medicare program-level
-- reconciliation/provenance evidence but do not add it as a second Medicare
-- federal-inflow path beside the CMS-native Medicare accounting stream.
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
    'MEDICARE',
    'MEDICARE_SHARED_SAVINGS_PROGRAM',
    'MSSP_EARN_SAVE_LOSS',
    'CMS_NATIVE_MEDICARE',
    'CMS_NATIVE_MEDICARE',
    ARRAY['CMS_MSSP_EARNSAVELOSS']::TEXT[],
    'EXCLUDE_DUPLICATE',
    $basis$
WCFFBP no-additive-by-default accounting invariant: no federal expenditure
source is additive merely because it appears as a distinct program, dataset,
financial field, award stream, or reporting system. A candidate source must
pass overlap reconciliation demonstrating that it represents economically
distinct federal dollars not already represented by the preferred accounting
source before receiving an additional plus sign in the principal ledger.

For the Medicare Shared Savings Program (MSSP), CMS EarnSaveLoss represents
the financial result of annual ACO reconciliation: earned shared-savings
payments or shared losses owed to Medicare. These are Medicare financial
transactions associated with the Medicare Trust Funds. Earned shared-savings
payments are Medicare outflows, while shared-loss recoveries are Medicare
receipts. Where WCFFBP uses CMS-native Medicare Trust Fund expenditure
accounting as its principal Medicare accounting path, separately adding
EarnSaveLoss would create a second accounting path for Medicare Trust Fund
transactions already represented within that broader accounting universe.

Accordingly, CMS MSSP EarnSaveLoss is retained as program-level
reconciliation/provenance evidence and is not separately additive to the
principal Medicare federal-inflow ledger. This classification does not mean
that an earned MSSP shared-savings payment is not federal spending. Rather,
it means that the payment must not be added a second time when the preferred
CMS-native Medicare accounting source already captures the Medicare Trust
Fund expenditure universe containing that transaction.

WCFFBP separately certified the MSSP geographic evidence chain. County-level
assigned-beneficiary sources were linked to MSSP financial results, public
suppression semantics were characterized, assumption-minimal Washington
beneficiary-incidence bounds were constructed, auxiliary person-year and
enrollment-type fields were tested and rejected as materially useful
estimators, and EarnSaveLoss geographic sensitivity was quantified using
signed interval arithmetic. The v1.1 financial-sensitivity execution passed
71 of 71 checks. Those geographic results remain valid analytical and
reconciliation evidence but do not authorize a separate additive Medicare
ledger entry.

No modeled geographic sensitivity scenario, midpoint, visible-only share,
person-year share, organizational connection, or other MSSP-derived
geographic measure is adopted by this policy as an independent principal
Medicare accounting or allocation source.

The original 2015 MSSP assigned-beneficiary-by-county source artifact was not
recovered from currently accessible CMS sources. Therefore 2015 geographic
allocation remains NOT ESTIMATED and is not imputed from adjacent years.
For 2016, county-source blank encoding remains
UNRESOLVED_HISTORICAL_ENCODING; that caveat is preserved. The 2019 regular
and 2019A off-cycle participation periods remain distinct analytical
observations and are not deduplicated merely because an ACO may appear in
both participation periods.

The empirically certified MSSP geographic and financial evidence covered
2016 through 2024, including the distinct 2019A off-cycle participation
period. The policy validity interval recorded here is therefore FY2016-
FY2024. This interval expresses the certified WCFFBP evidence coverage and
does not assert that MSSP accounting treatment outside that interval has
been empirically certified by this migration.

No MSSP EarnSaveLoss amount may receive an additional plus sign in the
principal WCFFBP Medicare ledger unless later evidence affirmatively
demonstrates economically distinct federal dollars not already represented
by the CMS-native Medicare accounting path.
$basis$,
    'ANALYSIS-168-v1',
    2016,
    2024
WHERE NOT EXISTS (
    SELECT 1
    FROM reference.federal_inflow_source_policy p
    WHERE p.inflow_family = 'MEDICARE'
      AND p.inflow_subfamily = 'MEDICARE_SHARED_SAVINGS_PROGRAM'
      AND p.accounting_measure = 'MSSP_EARN_SAVE_LOSS'
      AND p.methodology_version = 'ANALYSIS-168-v1'
);

-- Certification: exactly one natural policy row must exist and its
-- fail-closed treatment/source relationships and evidence interval must
-- remain intact.
DO $$
DECLARE
    policy_count INTEGER;
    v_preferred_source TEXT;
    v_allocation_source TEXT;
    v_overlapping_sources TEXT[];
    v_ledger_treatment TEXT;
    v_fy_start INTEGER;
    v_fy_end INTEGER;
BEGIN
    SELECT
        COUNT(*),
        MIN(preferred_source),
        MIN(allocation_source),
        (array_agg(overlapping_sources))[1],
        MIN(ledger_treatment),
        MIN(valid_from_fiscal_year),
        MIN(valid_through_fiscal_year)
    INTO
        policy_count,
        v_preferred_source,
        v_allocation_source,
        v_overlapping_sources,
        v_ledger_treatment,
        v_fy_start,
        v_fy_end
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'MEDICARE'
      AND inflow_subfamily = 'MEDICARE_SHARED_SAVINGS_PROGRAM'
      AND accounting_measure = 'MSSP_EARN_SAVE_LOSS'
      AND methodology_version = 'ANALYSIS-168-v1';

    IF policy_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-168 certification failed: expected exactly 1 policy row, found %',
            policy_count;
    END IF;

    IF v_preferred_source <> 'CMS_NATIVE_MEDICARE' THEN
        RAISE EXCEPTION
            'ETL-168 certification failed: preferred_source=%',
            v_preferred_source;
    END IF;

    IF v_allocation_source <> 'CMS_NATIVE_MEDICARE' THEN
        RAISE EXCEPTION
            'ETL-168 certification failed: allocation_source=%',
            v_allocation_source;
    END IF;

    IF v_ledger_treatment <> 'EXCLUDE_DUPLICATE' THEN
        RAISE EXCEPTION
            'ETL-168 certification failed: ledger_treatment=%',
            v_ledger_treatment;
    END IF;

    IF NOT ('CMS_MSSP_EARNSAVELOSS' = ANY(v_overlapping_sources)) THEN
        RAISE EXCEPTION
            'ETL-168 certification failed: CMS_MSSP_EARNSAVELOSS missing from overlapping_sources=%',
            v_overlapping_sources;
    END IF;

    IF v_fy_start <> 2016 OR v_fy_end <> 2024 THEN
        RAISE EXCEPTION
            'ETL-168 certification failed: expected FY2016-FY2024, found FY%-FY%',
            v_fy_start,
            v_fy_end;
    END IF;

    RAISE NOTICE
        'ETL-168 PASS: MSSP EarnSaveLoss retained as reconciliation/provenance evidence and excluded as a separately additive Medicare inflow; CMS-native Medicare accounting/allocation preferred; certified evidence interval FY2016-FY2024.';
END
$$;

COMMIT;

-- Read-only post-migration inspection:
SELECT
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    source_selection_basis
FROM reference.federal_inflow_source_policy
WHERE inflow_family = 'MEDICARE'
  AND inflow_subfamily = 'MEDICARE_SHARED_SAVINGS_PROGRAM'
  AND accounting_measure = 'MSSP_EARN_SAVE_LOSS'
  AND methodology_version = 'ANALYSIS-168-v1';