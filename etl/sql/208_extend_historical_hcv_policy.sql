\pset pager off
\set ON_ERROR_STOP on

\echo '============================================================'
\echo 'ETL-208 - HISTORICAL HCV POLICY EXTENSION'
\echo 'ANALYSIS-208-v1'
\echo 'FY2018-FY2019 ONLY'
\echo '============================================================'

BEGIN;

-- ============================================================
-- 1. PREFLIGHT: VERIFY SOURCE CONTROLS AND POLICY STATE
-- ============================================================

DO $$
DECLARE
    v_2018_count bigint;
    v_2019_count bigint;
    v_2018_amount numeric;
    v_2019_amount numeric;
BEGIN
    SELECT COUNT(*), COALESCE(SUM(federal_action_obligation), 0)
    INTO v_2018_count, v_2018_amount
    FROM analysis.v_certified_assistance_ledger
    WHERE load_batch_id = 20
      AND action_date_fiscal_year = 2018
      AND TRIM(cfda_number) = '14.871';

    SELECT COUNT(*), COALESCE(SUM(federal_action_obligation), 0)
    INTO v_2019_count, v_2019_amount
    FROM analysis.v_certified_assistance_ledger
    WHERE load_batch_id = 21
      AND action_date_fiscal_year = 2019
      AND TRIM(cfda_number) = '14.871';

    IF v_2018_count <> 894
       OR v_2018_amount <> 604856102.00
       OR v_2019_count <> 694
       OR v_2019_amount <> 632630308.00
    THEN
        RAISE EXCEPTION
            'ETL-208 ABORT: historical HCV controls differ from certification';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_source_policy
        WHERE federal_inflow_source_policy_id = 29
          AND methodology_version = 'ANALYSIS-174B-5Y-v1'
          AND valid_from_fiscal_year = 2020
          AND valid_through_fiscal_year = 2024
          AND preferred_source = 'USASPENDING_ASSISTANCE'
          AND accounting_measure = 'NET_FEDERAL_ACTION_OBLIGATION'
          AND allocation_source = 'UNRESOLVED'
          AND ledger_treatment = 'INCLUDE'
    ) THEN
        RAISE EXCEPTION
            'ETL-208 ABORT: original HCV source policy differs from expected state';
    END IF;

    IF (
        SELECT COUNT(*)
        FROM reference.federal_inflow_program_classification
        WHERE source_system = 'USASPENDING_ASSISTANCE'
          AND source_program_code = '14.871'
          AND methodology_version = 'ANALYSIS-174B-5Y-v1'
          AND valid_from_fiscal_year = 2020
          AND valid_through_fiscal_year = 2024
    ) <> 1 THEN
        RAISE EXCEPTION
            'ETL-208 ABORT: original HCV program classification not uniquely verified';
    END IF;

    IF (
        SELECT COUNT(*)
        FROM reference.federal_inflow_program_policy_mapping
        WHERE source_system = 'USASPENDING_ASSISTANCE'
          AND source_program_code = '14.871'
          AND methodology_version = 'ANALYSIS-174B-5Y-v1'
          AND federal_inflow_source_policy_id = 29
          AND resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
          AND valid_from_fiscal_year = 2020
          AND valid_through_fiscal_year = 2024
    ) <> 1 THEN
        RAISE EXCEPTION
            'ETL-208 ABORT: original HCV program mapping not uniquely verified';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM reference.federal_inflow_source_policy
        WHERE methodology_version = 'ANALYSIS-208-v1'
    )
    OR EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_classification
        WHERE methodology_version = 'ANALYSIS-208-v1'
    )
    OR EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_policy_mapping
        WHERE methodology_version = 'ANALYSIS-208-v1'
    )
    THEN
        RAISE EXCEPTION
            'ETL-208 ABORT: methodology version already exists; no overwrite permitted';
    END IF;

    RAISE NOTICE
        'ETL-208 preflight PASS: FY2018 %, FY2019 %',
        v_2018_amount, v_2019_amount;
END
$$;

-- ============================================================
-- 2. CREATE HISTORICAL SOURCE POLICY
-- ============================================================

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
    'ETL-208 historical extension of ANALYSIS-174B-5Y-v1. '
    || 'ETL-207A through ETL-207F certified 1,588 Washington '
    || 'Housing Choice Voucher transactions for FY2018-FY2019, '
    || 'with $1,237,486,410.00 net federal action obligations. '
    || 'Raw-to-certified transaction linkage, Washington state '
    || 'geography, HUD agency attribution, and recipient identity '
    || 'passed without exceptions. Historical award-key and FAIN '
    || 'collision checks against other HUD assistance programs '
    || 'found no exact matches. USAspending net federal action '
    || 'obligations are the statewide accounting measure. '
    || 'HUD VMS is retained as potentially overlapping, nonadditive '
    || 'validation evidence under the established HCV methodology; '
    || 'a separate FY2018-FY2019 VMS reconciliation was not performed. '
    || 'COVID and extraordinary classifications remain provenance '
    || 'dimensions. County beneficiary incidence is unresolved; '
    || 'PHA administrative geography is not a certified allocation.'
    AS source_selection_basis,
    'ANALYSIS-208-v1',
    2018,
    2019,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM reference.federal_inflow_source_policy
WHERE federal_inflow_source_policy_id = 29;

-- ============================================================
-- 3. CREATE HISTORICAL PROGRAM CLASSIFICATION
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
SELECT
    source_system,
    source_program_code,
    source_program_title,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    covid_relevance,
    extraordinary_relevance,
    'ETL-208: historical FY2018-FY2019 extension of '
    || 'ANALYSIS-174B-5Y-v1. Source geography and lineage '
    || 'certified by ETL-207A through ETL-207F. '
    || 'The existing HCV accounting-stage overlap rationale '
    || 'is applied to historical USAspending obligations. '
    || 'No independent historical HUD VMS reconciliation '
    || 'is claimed. County incidence remains unresolved.',
    'ANALYSIS-208-v1',
    2018,
    2019,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM reference.federal_inflow_program_classification
WHERE federal_inflow_program_classification_id = 80;

-- ============================================================
-- 4. CREATE HISTORICAL PROGRAM POLICY MAPPING
-- ============================================================

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
    '14.871',
    p.federal_inflow_source_policy_id,
    'INCLUDE_ADDITIVE',
    'ETL-208: FY2018-FY2019 historical HCV statewide additive '
    || 'accounting extension. USAspending net federal action '
    || 'obligations are counted once. HUD VMS is nonadditive '
    || 'overlapping validation evidence. County allocation '
    || 'remains unresolved.',
    'ANALYSIS-208-v1',
    2018,
    2019,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM reference.federal_inflow_source_policy p
WHERE p.methodology_version = 'ANALYSIS-208-v1'
  AND p.inflow_family = 'HOUSING_ASSISTANCE'
  AND p.inflow_subfamily = 'HOUSING_CHOICE_VOUCHERS'
  AND p.valid_from_fiscal_year = 2018
  AND p.valid_through_fiscal_year = 2019;

-- ============================================================
-- 5. VERIFY NEW RECORDS BEFORE COMMIT
-- ============================================================

DO $$
DECLARE
    v_source_count integer;
    v_class_count integer;
    v_mapping_count integer;
    v_original_count integer;
BEGIN
    SELECT COUNT(*) INTO v_source_count
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version = 'ANALYSIS-208-v1'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019
      AND preferred_source = 'USASPENDING_ASSISTANCE'
      AND allocation_source = 'UNRESOLVED'
      AND accounting_measure = 'NET_FEDERAL_ACTION_OBLIGATION'
      AND ledger_treatment = 'INCLUDE';

    SELECT COUNT(*) INTO v_class_count
    FROM reference.federal_inflow_program_classification
    WHERE methodology_version = 'ANALYSIS-208-v1'
      AND source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '14.871'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    SELECT COUNT(*) INTO v_mapping_count
    FROM reference.federal_inflow_program_policy_mapping m
    JOIN reference.federal_inflow_source_policy p
      ON p.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id
    WHERE m.methodology_version = 'ANALYSIS-208-v1'
      AND m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code = '14.871'
      AND m.resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
      AND m.valid_from_fiscal_year = 2018
      AND m.valid_through_fiscal_year = 2019
      AND p.methodology_version = 'ANALYSIS-208-v1';

    SELECT COUNT(*) INTO v_original_count
    FROM reference.federal_inflow_program_policy_mapping
    WHERE federal_inflow_program_policy_mapping_id = 76
      AND federal_inflow_source_policy_id = 29
      AND methodology_version = 'ANALYSIS-174B-5Y-v1'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024
      AND resolved_accounting_disposition = 'INCLUDE_ADDITIVE';

    IF v_source_count <> 1
       OR v_class_count <> 1
       OR v_mapping_count <> 1
       OR v_original_count <> 1
    THEN
        RAISE EXCEPTION
            'ETL-208 verification FAILED: source %, class %, mapping %, original %',
            v_source_count,
            v_class_count,
            v_mapping_count,
            v_original_count;
    END IF;

    RAISE NOTICE
        'ETL-208 verification PASS: 3 historical policy records; original mapping preserved';
END
$$;

COMMIT;

\echo '============================================================'
\echo 'ETL-208 MIGRATION COMPLETE'
\echo '============================================================'