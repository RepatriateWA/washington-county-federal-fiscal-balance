
\pset pager off
\set ON_ERROR_STOP on

\echo '============================================================'
\echo 'ETL-209M - HISTORICAL MEDICAID POLICY EXTENSION'
\echo 'ANALYSIS-209M-v1 / FY2018-FY2019'
\echo '============================================================'

BEGIN;

-- 1. Preflight: certify historical source and CMS controls.
DO $$
DECLARE
    v_count bigint;
    v_amount numeric;
    v_cms_count bigint;
    v_cms_amount numeric;
    v_conflicts bigint;
BEGIN
    SELECT COUNT(*), ROUND(SUM(federal_action_obligation)::numeric, 2)
    INTO v_count, v_amount
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) = '93.778'
      AND (
           (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
      );

    IF v_count <> 53 OR v_amount <> 16453706376.00 THEN
        RAISE EXCEPTION
            'ETL-209M source mismatch: % transactions, $%',
            v_count, v_amount;
    END IF;

    SELECT COUNT(*), ROUND(SUM(m.federal_share)::numeric, 2)
    INTO v_cms_count, v_cms_amount
    FROM cms.medicaid_state_control_total m
    JOIN reference.state_registry s
      ON s.state_id = m.state_id
    WHERE s.state_abbreviation = 'WA'
      AND m.fiscal_year BETWEEN 2018 AND 2019
      AND m.expenditure_time_basis = 'FEDERAL_FISCAL_YEAR'
      AND m.control_total_label = 'Total Net Expenditures';

    IF v_cms_count <> 2 OR v_cms_amount <> 15801240644.00 THEN
        RAISE EXCEPTION
            'ETL-209M CMS control mismatch: % rows, $%',
            v_cms_count, v_cms_amount;
    END IF;

    IF (
        SELECT COUNT(*)
        FROM reference.federal_inflow_source_policy
        WHERE federal_inflow_source_policy_id = 7
          AND methodology_version = 'ANALYSIS-174B-4B-MEDICAID-v1'
          AND preferred_source = 'CMS_NATIVE_MEDICAID'
          AND allocation_source = 'CMS_NATIVE_MEDICAID'
          AND ledger_treatment = 'EXCLUDE_DUPLICATE'
          AND valid_from_fiscal_year = 2020
          AND valid_through_fiscal_year = 2024
    ) <> 1 THEN
        RAISE EXCEPTION
            'ETL-209M original Medicaid source policy changed';
    END IF;

    IF (
        SELECT COUNT(*)
        FROM reference.federal_inflow_program_policy_mapping
        WHERE federal_inflow_program_policy_mapping_id = 5
          AND federal_inflow_source_policy_id = 7
          AND source_system = 'USASPENDING_ASSISTANCE'
          AND source_program_code = '93.778'
          AND resolved_accounting_disposition = 'EXCLUDE_DUPLICATE'
          AND methodology_version = 'ANALYSIS-174B-5L-v1'
          AND valid_from_fiscal_year = 2020
          AND valid_through_fiscal_year = 2024
    ) <> 1 THEN
        RAISE EXCEPTION
            'ETL-209M original Medicaid mapping changed';
    END IF;

    SELECT COUNT(*) INTO v_conflicts
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.778'
      AND COALESCE(valid_from_fiscal_year, -9999) <= 2019
      AND COALESCE(valid_through_fiscal_year, 9999) >= 2018;

    IF v_conflicts <> 0 THEN
        RAISE EXCEPTION
            'ETL-209M historical Medicaid policy collision: %',
            v_conflicts;
    END IF;

    IF EXISTS (
        SELECT 1 FROM reference.federal_inflow_source_policy
        WHERE methodology_version = 'ANALYSIS-209M-v1'
    )
    OR EXISTS (
        SELECT 1 FROM reference.federal_inflow_program_classification
        WHERE methodology_version = 'ANALYSIS-209M-v1'
    )
    OR EXISTS (
        SELECT 1 FROM reference.federal_inflow_program_policy_mapping
        WHERE methodology_version = 'ANALYSIS-209M-v1'
    ) THEN
        RAISE EXCEPTION
            'ETL-209M methodology already exists';
    END IF;

    RAISE NOTICE
        'ETL-209M PREFLIGHT PASS: source and CMS controls verified';
END
$$;

-- 2. Extend source policy without changing original.
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
    valid_through_fiscal_year,
    created_at,
    updated_at
)
SELECT
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    'ETL-209M historical extension of '
    || 'ANALYSIS-174B-4B-MEDICAID-v1. '
    || 'ETL-209L verified Washington CMS Medicaid '
    || 'Total Net Expenditures federal-share controls '
    || 'for FFY2018 ($7,542,439,851) and FFY2019 '
    || '($8,258,800,793). Historical USAspending '
    || 'AL 93.778 contains 53 transactions with '
    || '$16,453,706,376 in net federal action obligations. '
    || 'Award identifiers identify Medicaid entitlement '
    || 'and administration streams, including prior-year '
    || 'adjustments. USAspending obligations and CMS '
    || 'expenditures are different accounting measures; '
    || 'annual equality is neither expected nor claimed. '
    || 'CMS-native Medicaid is the preferred expenditure '
    || 'accounting path. USAspending AL 93.778 is '
    || 'nonadditive reconciliation and provenance evidence. '
    || 'Historical normalized Medicaid service detail '
    || 'is unavailable for FY2018-FY2019; independent '
    || 'service-category reconstruction is not claimed. '
    || 'County allocation is not certified by this migration. '
    || 'COVID and extraordinary funding flags remain '
    || 'independent provenance characteristics.',
    'ANALYSIS-209M-v1',
    2018,
    2019,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM reference.federal_inflow_source_policy
WHERE federal_inflow_source_policy_id = 7;


-- ============================================================
-- 3. CREATE HISTORICAL MEDICAID PROGRAM CLASSIFICATION
--
-- ETL-209M diagnostic confirmed no existing classification
-- for AL 93.778. Construct explicitly from certified
-- source evidence rather than copying a nonexistent row.
-- ============================================================

INSERT INTO reference.federal_inflow_program_classification (
    source_system,
    source_program_code,
    source_program_title,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    covid_relevance,
    extraordinary_relevance,
    classification_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    created_at,
    updated_at
)
VALUES (
    'USASPENDING_ASSISTANCE',
    '93.778',
    'Grants to States for Medicaid',
    'MEDICAID',
    'MEDICAID_STATE_EXPENDITURES',
    'HIGH',
    TRUE,
    FALSE,
    'ETL-209M: Historical FY2018-FY2019 Medicaid '
    || 'accounting classification. ETL-209L certified '
    || '53 Washington USAspending AL 93.778 transactions '
    || 'with $16,453,706,376.00 net federal action '
    || 'obligations. CMS-native Washington Medicaid '
    || 'Total Net Expenditures federal-share controls '
    || 'were verified for FFY2018 ($7,542,439,851) '
    || 'and FFY2019 ($8,258,800,793). '
    || 'Award identifiers and descriptions establish '
    || 'Medicaid entitlement and administrative streams '
    || 'with prior-year adjustments. '
    || 'USAspending obligations and CMS expenditures '
    || 'are distinct accounting measures. '
    || 'The historical USAspending stream is nonadditive '
    || 'to the preferred CMS-native expenditure control. '
    || 'Normalized service-category detail is unavailable '
    || 'for these years. County incidence remains '
    || 'unresolved. COVID provenance is preserved '
    || 'independently of accounting disposition.',
    'ANALYSIS-209M-v1',
    2018,
    2019,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
);


-- 4. Create historical mapping.
INSERT INTO reference.federal_inflow_program_policy_mapping (
    source_system,
    source_program_code,
    federal_inflow_source_policy_id,
    resolved_accounting_disposition,
    mapping_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    created_at,
    updated_at
)
SELECT
    'USASPENDING_ASSISTANCE',
    '93.778',
    p.federal_inflow_source_policy_id,
    'EXCLUDE_DUPLICATE',
    'ETL-209M: FY2018-FY2019 Medicaid AL 93.778 '
    || 'nonadditive source-policy extension. '
    || 'CMS-native federal expenditures are the '
    || 'preferred accounting control. USAspending '
    || 'obligations remain provenance and reconciliation '
    || 'evidence. No county incidence certification.',
    'ANALYSIS-209M-v1',
    2018,
    2019,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM reference.federal_inflow_source_policy p
WHERE p.methodology_version = 'ANALYSIS-209M-v1'
  AND p.inflow_family = 'MEDICAID'
  AND p.valid_from_fiscal_year = 2018
  AND p.valid_through_fiscal_year = 2019;

-- 5. Verify all three inserts and original preservation.
DO $$
DECLARE
    v_sources bigint;
    v_classes bigint;
    v_mappings bigint;
    v_original bigint;
BEGIN
    SELECT COUNT(*) INTO v_sources
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version = 'ANALYSIS-209M-v1'
      AND preferred_source = 'CMS_NATIVE_MEDICAID'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    SELECT COUNT(*) INTO v_classes
    FROM reference.federal_inflow_program_classification
    WHERE methodology_version = 'ANALYSIS-209M-v1'
      AND source_program_code = '93.778'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    SELECT COUNT(*) INTO v_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE methodology_version = 'ANALYSIS-209M-v1'
      AND source_program_code = '93.778'
      AND resolved_accounting_disposition = 'EXCLUDE_DUPLICATE'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    SELECT COUNT(*) INTO v_original
    FROM reference.federal_inflow_program_policy_mapping
    WHERE federal_inflow_program_policy_mapping_id = 5
      AND methodology_version = 'ANALYSIS-174B-5L-v1'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;

    IF v_sources <> 1
       OR v_classes <> 1
       OR v_mappings <> 1
       OR v_original <> 1 THEN
        RAISE EXCEPTION
            'ETL-209M verification failed: source %, class %, mapping %, original %',
            v_sources, v_classes, v_mappings, v_original;
    END IF;

    RAISE NOTICE
        'ETL-209M PASS: historical Medicaid policy inserted; original preserved';
END
$$;

COMMIT;

\echo 'ETL-209M MIGRATION COMPLETE'
