-- ETL-167
-- Seed Medicare Supplementary Medical Insurance / USAspending AL 93.774
-- overlap policy and the WCFFBP no-additive-by-default accounting invariant.
--
-- Evidence basis:
--   * USAspending AL 93.774 empirical profile v0.1
--   * USAspending AL 93.774 structural reconciliation v0.1
--   * Official USAspending Medicare aggregate-record documentation
--   * CMS-native Medicare accounting-source reconciliation
--
-- Policy:
--   * USAspending AL 93.774 is retained as overlap/reconciliation/provenance
--     evidence; it is not an additional additive Medicare inflow path.
--   * USAspending Medicare aggregate-record recipient/place geography is not
--     a beneficiary-incidence county-allocation basis.
--   * No federal expenditure source is additive by default. A candidate source
--     must pass overlap reconciliation demonstrating an economically distinct
--     federal payment stream before principal-ledger inclusion.
--
-- This migration changes policy metadata only. It does not alter source
-- observations, reconstructed CMS amounts, or county allocations.

BEGIN;

-- Fail closed if the established policy table does not have the architecture
-- expected from ETL-135 / ETL-149 / ETL-157 / ETL-158.
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
            'ETL-167 expected reference.federal_inflow_source_policy columns are missing: %',
            missing_columns;
    END IF;
END
$$;

-- The established ledger_treatment vocabulary does not include a literal
-- OVERLAPPING value. EXCLUDE_DUPLICATE is therefore the fail-closed ledger
-- treatment: preserve the source as overlap evidence but do not add it as a
-- second Medicare inflow path.
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
    'SUPPLEMENTARY_MEDICAL_INSURANCE',
    'ANNUAL_MEDICARE_PAYMENT_STREAMS',
    'CMS_NATIVE_MEDICARE',
    'CMS_NATIVE_MEDICARE',
    ARRAY['USASPENDING_ASSISTANCE_93.774']::TEXT[],
    'EXCLUDE_DUPLICATE',
    $basis$
WCFFBP no-additive-by-default accounting invariant: no federal expenditure
source is additive merely because it appears in a different federal dataset.
A candidate source must pass overlap reconciliation demonstrating that it
represents an economically distinct federal payment stream before inclusion
in the principal ledger. Alternative representations of the same underlying
expenditure are retained as controls, reconciliation evidence, or provenance
rather than added together.

For Medicare Supplementary Medical Insurance, USAspending Assistance Listing
93.774 is retained as overlap/reconciliation/provenance evidence and is not
an additional additive path beside CMS-native Medicare accounting streams.
WCFFBP empirical profiling found 139 normalized 93.774 transactions for
FY2020-FY2025 with $3,484,701,356.34 in net federal action obligations, one
recipient name (MULTIPLE RECIPIENTS), four Washington places of performance,
and aggregate ASST_AGG award identifiers. Structural reconciliation balanced
all transaction, annual, award, place, and award-place obligation identities.
Official USAspending Medicare aggregate-record documentation explains that
Medicare Assistance Listings including 93.774 are reported as aggregate
records associated with Medicare Administrative Contractors; recipient and
place-of-performance geography reflects that reporting structure rather than
beneficiary/provider incidence. Accordingly, USAspending 93.774 geography is
not a WCFFBP county-allocation basis. CMS-native Medicare sources remain the
preferred accounting/allocation path for the Medicare components separately
certified by WCFFBP. No component of 93.774 may receive an additional plus sign
unless later evidence affirmatively establishes economically distinct dollars
not already represented by the CMS-native Medicare path.
$basis$,
    'ANALYSIS-167-v1',
    2020,
    2025
WHERE NOT EXISTS (
    SELECT 1
    FROM reference.federal_inflow_source_policy p
    WHERE p.inflow_family = 'MEDICARE'
      AND p.inflow_subfamily = 'SUPPLEMENTARY_MEDICAL_INSURANCE'
      AND p.accounting_measure = 'ANNUAL_MEDICARE_PAYMENT_STREAMS'
      AND p.methodology_version = 'ANALYSIS-167-v1'
);

-- Certification: exactly one natural policy row must exist and its
-- fail-closed treatment/source relationships must be intact.
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
      AND inflow_subfamily = 'SUPPLEMENTARY_MEDICAL_INSURANCE'
      AND accounting_measure = 'ANNUAL_MEDICARE_PAYMENT_STREAMS'
      AND methodology_version = 'ANALYSIS-167-v1';

    IF policy_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-167 certification failed: expected exactly 1 policy row, found %',
            policy_count;
    END IF;

    IF v_preferred_source <> 'CMS_NATIVE_MEDICARE' THEN
        RAISE EXCEPTION
            'ETL-167 certification failed: preferred_source=%',
            v_preferred_source;
    END IF;

    IF v_allocation_source <> 'CMS_NATIVE_MEDICARE' THEN
        RAISE EXCEPTION
            'ETL-167 certification failed: allocation_source=%',
            v_allocation_source;
    END IF;

    IF v_ledger_treatment <> 'EXCLUDE_DUPLICATE' THEN
        RAISE EXCEPTION
            'ETL-167 certification failed: ledger_treatment=%',
            v_ledger_treatment;
    END IF;

    IF NOT ('USASPENDING_ASSISTANCE_93.774' = ANY(v_overlapping_sources)) THEN
        RAISE EXCEPTION
            'ETL-167 certification failed: 93.774 missing from overlapping_sources=%',
            v_overlapping_sources;
    END IF;

    IF v_fy_start <> 2020 OR v_fy_end <> 2025 THEN
        RAISE EXCEPTION
            'ETL-167 certification failed: expected FY2020-FY2025, found FY%-FY%',
            v_fy_start, v_fy_end;
    END IF;

    RAISE NOTICE
        'ETL-167 PASS: Medicare SMI policy seeded; USAspending 93.774 excluded as overlapping, CMS-native accounting/allocation preferred, FY2020-FY2025.';
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
  AND inflow_subfamily = 'SUPPLEMENTARY_MEDICAL_INSURANCE'
  AND methodology_version = 'ANALYSIS-167-v1';
