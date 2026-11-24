-- =====================================================================
-- WCFFBP ETL-211H
-- HISTORICAL MEDICARE ASSISTANCE EXCLUSION POLICY
-- FY2018-FY2019 | AL 93.773 AND 93.774
--
-- CONTROLLED DATABASE MIGRATION
-- Two program-policy mappings only.
--
-- No CMS Medicare expenditure authorization.
-- No federal fiscal-year conversion.
-- No changes to FY2020-FY2024 policy mappings.
-- =====================================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '================================================================'
\echo 'ETL-211H - HISTORICAL MEDICARE EXCLUSION POLICY'
\echo '================================================================'

BEGIN;

-- ============================================================
-- 1. PRE-MIGRATION ASSERTIONS
-- ============================================================

\echo ''
\echo '1. PRE-MIGRATION ASSERTIONS'

DO $$
DECLARE
    v_rows bigint;
    v_distinct bigint;
    v_net numeric;
    v_original_mappings bigint;
    v_conflicting_mappings bigint;
    v_award_overrides bigint;
    v_source_policies bigint;
    v_cms_authorized bigint;
BEGIN

    -- Historical USAspending controls.

    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),
        COALESCE(SUM(federal_action_obligation), 0)
    INTO
        v_rows,
        v_distinct,
        v_net
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) IN ('93.773', '93.774')
      AND (
          (load_batch_id = 20
           AND action_date_fiscal_year = 2018)
       OR (load_batch_id = 21
           AND action_date_fiscal_year = 2019)
      );

    IF v_rows <> 36
       OR v_distinct <> 36
       OR ROUND(v_net, 2) <> 2489730308.00
    THEN
        RAISE EXCEPTION
            'ETL-211H FAIL: historical transaction controls';
    END IF;

    -- Existing FY2020-FY2024 mappings must be unchanged.

    SELECT COUNT(*)
    INTO v_original_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND (
          (
              source_program_code = '93.773'
              AND federal_inflow_source_policy_id = 9
          )
          OR
          (
              source_program_code = '93.774'
              AND federal_inflow_source_policy_id = 5
          )
      )
      AND resolved_accounting_disposition = 'EXCLUDE_DUPLICATE'
      AND methodology_version = 'ANALYSIS-174B-5L-v1'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;

    IF v_original_mappings <> 2 THEN
        RAISE EXCEPTION
            'ETL-211H FAIL: original Medicare mappings not preserved';
    END IF;

    -- No existing historical program mappings.

    SELECT COUNT(*)
    INTO v_conflicting_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code IN ('93.773', '93.774')
      AND COALESCE(valid_from_fiscal_year, -9999) <= 2019
      AND COALESCE(valid_through_fiscal_year, 9999) >= 2018;

    IF v_conflicting_mappings <> 0 THEN
        RAISE EXCEPTION
            'ETL-211H FAIL: historical mappings already exist';
    END IF;

    -- No historical award-level overrides.

    SELECT COUNT(*)
    INTO v_award_overrides
    FROM reference.federal_inflow_award_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code IN ('93.773', '93.774')
      AND COALESCE(valid_from_fiscal_year, -9999) <= 2019
      AND COALESCE(valid_through_fiscal_year, 9999) >= 2018;

    IF v_award_overrides <> 0 THEN
        RAISE EXCEPTION
            'ETL-211H FAIL: historical award overrides exist';
    END IF;

    -- Established Medicare source policies must exist.

    SELECT COUNT(*)
    INTO v_source_policies
    FROM reference.federal_inflow_source_policy
    WHERE
        (
            federal_inflow_source_policy_id = 9
            AND inflow_family = 'MEDICARE'
            AND inflow_subfamily = 'HOSPITAL_INSURANCE'
            AND preferred_source = 'CMS_NATIVE_MEDICARE'
            AND ledger_treatment = 'EXCLUDE_DUPLICATE'
        )
        OR
        (
            federal_inflow_source_policy_id = 5
            AND inflow_family = 'MEDICARE'
            AND inflow_subfamily = 'SUPPLEMENTARY_MEDICAL_INSURANCE'
            AND preferred_source = 'CMS_NATIVE_MEDICARE'
            AND ledger_treatment = 'EXCLUDE_DUPLICATE'
        );

    IF v_source_policies <> 2 THEN
        RAISE EXCEPTION
            'ETL-211H FAIL: Medicare source-policy lineage';
    END IF;

    -- No CMS Medicare core authorization for CY2018-CY2019.

    SELECT COUNT(*)
    INTO v_cms_authorized
    FROM cms.medicare_core_state_year
    WHERE calendar_year IN (2018, 2019)
      AND state_id = 48
      AND (
          ledger_status <> 'NOT_YET_AUTHORIZED'
          OR timing_basis_status NOT LIKE
             '%FFY_CONVERSION_NOT_AUTHORIZED%'
      );

    IF v_cms_authorized <> 0 THEN
        RAISE EXCEPTION
            'ETL-211H FAIL: unexpected CMS ledger authorization';
    END IF;

    RAISE NOTICE
        'ETL-211H PRECHECK PASS: 36 historical transactions; original mappings intact; no conflicts';

END $$;

-- ============================================================
-- 2. INSERT HISTORICAL POLICY MAPPINGS
-- ============================================================

\echo ''
\echo '2. INSERT HISTORICAL PROGRAM MAPPINGS'

INSERT INTO reference.federal_inflow_program_policy_mapping (
    source_system,
    source_program_code,
    federal_inflow_source_policy_id,
    resolved_accounting_disposition,
    mapping_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
)
VALUES
(
    'USASPENDING_ASSISTANCE',
    '93.773',
    9,
    'EXCLUDE_DUPLICATE',
    'ETL-211F evidence review and ETL-211G preflight: '
    || 'FY2018-FY2019 Medicare Hospital Insurance USAspending '
    || 'aggregate obligations are overlapping Medicare-program '
    || 'provenance, not an additive CMS payment stream. '
    || 'Program-level classification; no transaction-level '
    || 'CMS dollar matching or FFY expenditure authorization.',
    'ANALYSIS-211H-HISTORICAL-MEDICARE-v1',
    2018,
    2019
),
(
    'USASPENDING_ASSISTANCE',
    '93.774',
    5,
    'EXCLUDE_DUPLICATE',
    'ETL-211F evidence review and ETL-211G preflight: '
    || 'FY2018-FY2019 Medicare Supplementary Medical Insurance '
    || 'USAspending aggregate obligations are overlapping '
    || 'Medicare-program provenance, not an additive CMS payment '
    || 'stream. Program-level classification; no transaction-level '
    || 'CMS dollar matching or FFY expenditure authorization.',
    'ANALYSIS-211H-HISTORICAL-MEDICARE-v1',
    2018,
    2019
);

-- ============================================================
-- 3. POST-MIGRATION ASSERTIONS
-- ============================================================

\echo ''
\echo '3. POST-MIGRATION ASSERTIONS'

DO $$
DECLARE
    v_new bigint;
    v_original bigint;
    v_bad bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_new
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code IN ('93.773', '93.774')
      AND methodology_version =
          'ANALYSIS-211H-HISTORICAL-MEDICARE-v1'
      AND resolved_accounting_disposition = 'EXCLUDE_DUPLICATE'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    IF v_new <> 2 THEN
        RAISE EXCEPTION
            'ETL-211H FAIL: expected exactly two historical mappings; found %',
            v_new;
    END IF;

    SELECT COUNT(*)
    INTO v_original
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code IN ('93.773', '93.774')
      AND methodology_version = 'ANALYSIS-174B-5L-v1'
      AND resolved_accounting_disposition = 'EXCLUDE_DUPLICATE'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;

    IF v_original <> 2 THEN
        RAISE EXCEPTION
            'ETL-211H FAIL: original FY2020-FY2024 mappings changed';
    END IF;

    SELECT COUNT(*)
    INTO v_bad
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code IN ('93.773', '93.774')
      AND (
          resolved_accounting_disposition <> 'EXCLUDE_DUPLICATE'
          OR valid_from_fiscal_year IS NULL
          OR valid_through_fiscal_year IS NULL
      );

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'ETL-211H FAIL: unexpected Medicare policy mappings';
    END IF;

    RAISE NOTICE
        'ETL-211H POSTCHECK PASS: two historical exclusion mappings inserted; original mappings preserved';

END $$;

-- ============================================================
-- 4. DISPLAY FINAL POLICY STATE
-- ============================================================

\echo ''
\echo '4. FINAL MEDICARE PROGRAM POLICY STATE'

SELECT
    source_program_code,
    federal_inflow_source_policy_id,
    resolved_accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code IN ('93.773', '93.774')
ORDER BY
    source_program_code,
    valid_from_fiscal_year;

COMMIT;

\echo ''
\echo 'ETL-211H COMPLETE - HISTORICAL MEDICARE POLICY COMMITTED'