
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-211N5B - HISTORICAL VA PURCHASE CARE POLICY'
\echo 'AL 64.029 / FY2018-FY2019'
\echo 'ANALYSIS-211N-v1'
\echo 'TRANSACTIONAL DATABASE MIGRATION'
\echo '============================================================'

BEGIN;

-- Prevent concurrent changes while validating and inserting.
LOCK TABLE
    reference.federal_inflow_program_classification,
    reference.federal_inflow_source_policy,
    reference.federal_inflow_program_policy_mapping
IN SHARE ROW EXCLUSIVE MODE;

\echo ''
\echo '1. PRE-MIGRATION CONTROLS'

DO $$
DECLARE
    v_count bigint;
    v_total numeric;
    v_policy_id bigint;
    v_mapping_id bigint;
BEGIN
    -- Refuse duplicate execution.
    SELECT
        (SELECT COUNT(*)
         FROM reference.federal_inflow_program_classification
         WHERE methodology_version = 'ANALYSIS-211N-v1')
      + (SELECT COUNT(*)
         FROM reference.federal_inflow_source_policy
         WHERE methodology_version = 'ANALYSIS-211N-v1')
      + (SELECT COUNT(*)
         FROM reference.federal_inflow_program_policy_mapping
         WHERE methodology_version = 'ANALYSIS-211N-v1')
    INTO v_count;

    IF v_count <> 0 THEN
        RAISE EXCEPTION
            'PRECHECK FAILED: ANALYSIS-211N-v1 already exists';
    END IF;

    -- No competing historical classification or mapping.
    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_program_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '64.029'
      AND COALESCE(valid_from_fiscal_year, -9999) <= 2019
      AND COALESCE(valid_through_fiscal_year, 9999) >= 2018;

    IF v_count <> 0 THEN
        RAISE EXCEPTION
            'PRECHECK FAILED: historical classification collision';
    END IF;

    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '64.029'
      AND COALESCE(valid_from_fiscal_year, -9999) <= 2019
      AND COALESCE(valid_through_fiscal_year, 9999) >= 2018;

    IF v_count <> 0 THEN
        RAISE EXCEPTION
            'PRECHECK FAILED: historical policy mapping collision';
    END IF;

    -- Preserve established later-year precedent.
    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_program_policy_mapping m
    JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id
    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code = '64.029'
      AND m.methodology_version = 'ANALYSIS-174B-5N-v1'
      AND m.valid_from_fiscal_year = 2020
      AND m.valid_through_fiscal_year = 2024
      AND m.resolved_accounting_disposition =
          'EXCLUDE_DUPLICATE'
      AND s.preferred_source = 'VA_GDX'
      AND s.allocation_source = 'VA_GDX'
      AND s.ledger_treatment = 'EXCLUDE_DUPLICATE';

    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'PRECHECK FAILED: later-year precedent not unique';
    END IF;

    -- Verify certified historical transaction controls.
    SELECT
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0)
    INTO v_count, v_total
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) = '64.029'
      AND (
          (load_batch_id = 20
           AND action_date_fiscal_year = 2018)
          OR
          (load_batch_id = 21
           AND action_date_fiscal_year = 2019)
      );

    IF v_count <> 936 OR v_total <> 317136584.00 THEN
        RAISE EXCEPTION
            'PRECHECK FAILED: transaction control %, %',
            v_count, v_total;
    END IF;

    RAISE NOTICE
        'ETL-211N5B PRE-MIGRATION CONTROLS PASS';

    -- One historical program classification.
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
        valid_through_fiscal_year
    )
    VALUES (
        'USASPENDING_ASSISTANCE',
        '64.029',
        'PURCHASE CARE PROGRAM',
        'VETERANS',
        'VETERANS_PROGRAM',
        'KNOWN_OVERLAP',
        FALSE,
        FALSE,
        'FY2018-FY2019 Purchase Care Program historical '
        || 'reconciliation. ETL-211N2 through ETL-211N4 '
        || 'establish 936 certified transactions totaling '
        || '$317,136,584 in obligations. All FY2019 '
        || 'transactions and 195 FY2018 transactions are '
        || 'described as COMMUNITY CARE PAYMENTS. '
        || 'The remaining 273 FY2018 transactions have '
        || 'missing descriptions. Historical VA GDX Medical '
        || 'Care is available for all 39 Washington counties '
        || 'and has preserved source-file checksums. '
        || 'Functional overlap and the FY2020-FY2024 '
        || 'exclusion precedent support source preference; '
        || 'transaction-level GDX containment has not '
        || 'been independently demonstrated.',
        'ANALYSIS-211N-v1',
        2018,
        2019
    );

    -- One historical source policy.
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
        'VETERANS_AFFAIRS',
        'VA_GDX_PURCHASE_CARE_OVERLAP',
        'VA expenditures',
        'VA_GDX',
        'VA_GDX',
        ARRAY['USASPENDING_ASSISTANCE']::text[],
        'EXCLUDE_DUPLICATE',
        'FY2018-FY2019 historical AL 64.029 source preference. '
        || 'VA GDX Medical Care is the preferred accounting '
        || 'and county allocation source. The Purchase Care '
        || 'Program is functionally associated with VA '
        || 'Community Care payments, and FY2020-FY2024 '
        || 'policy ANALYSIS-174B-5N-v1 excludes the same '
        || 'program as duplicate. FY2018 and FY2019 GDX '
        || 'sources use LEGACY_PRE_FY2024 methodology. '
        || 'USAspending obligations remain transaction-level '
        || 'provenance and are not an additional expenditure '
        || 'stream. Obligations and expenditures differ in '
        || 'accounting measure and timing. Complete '
        || 'transaction-level containment is not proven; '
        || '273 FY2018 transaction descriptions are missing.',
        'ANALYSIS-211N-v1',
        2018,
        2019
    )
    RETURNING federal_inflow_source_policy_id
    INTO v_policy_id;

    -- Mapping IDs are explicitly assigned in this schema.
    SELECT COALESCE(
        MAX(federal_inflow_program_policy_mapping_id), 0
    ) + 1
    INTO v_mapping_id
    FROM reference.federal_inflow_program_policy_mapping;

    INSERT INTO reference.federal_inflow_program_policy_mapping (
        federal_inflow_program_policy_mapping_id,
        source_system,
        source_program_code,
        federal_inflow_source_policy_id,
        resolved_accounting_disposition,
        mapping_basis,
        methodology_version,
        valid_from_fiscal_year,
        valid_through_fiscal_year
    )
    VALUES (
        v_mapping_id,
        'USASPENDING_ASSISTANCE',
        '64.029',
        v_policy_id,
        'EXCLUDE_DUPLICATE',
        'Historical AL 64.029 Purchase Care Program '
        || 'FY2018-FY2019. VA GDX Medical Care preferred. '
        || '936 transactions and $317,136,584 obligations '
        || 'are nonadditive provenance. Functional overlap '
        || 'and later-year precedent support exclusion; '
        || 'transaction-level containment is not independently '
        || 'proven. ETL-211N2/N3/N4 evidence retained.',
        'ANALYSIS-211N-v1',
        2018,
        2019
    );

    RAISE NOTICE
        'ETL-211N5B INSERTS COMPLETED: policy %, mapping %',
        v_policy_id, v_mapping_id;
END
$$;

\echo ''
\echo '2. POST-MIGRATION CONTROLS'

DO $$
DECLARE
    v_classifications bigint;
    v_policies bigint;
    v_mappings bigint;
    v_valid bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_classifications
    FROM reference.federal_inflow_program_classification
    WHERE methodology_version = 'ANALYSIS-211N-v1';

    SELECT COUNT(*)
    INTO v_policies
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version = 'ANALYSIS-211N-v1';

    SELECT COUNT(*)
    INTO v_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE methodology_version = 'ANALYSIS-211N-v1';

    SELECT COUNT(*)
    INTO v_valid
    FROM reference.federal_inflow_program_policy_mapping m
    JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id
    WHERE m.methodology_version = 'ANALYSIS-211N-v1'
      AND m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code = '64.029'
      AND m.valid_from_fiscal_year = 2018
      AND m.valid_through_fiscal_year = 2019
      AND m.resolved_accounting_disposition =
          'EXCLUDE_DUPLICATE'
      AND s.methodology_version = 'ANALYSIS-211N-v1'
      AND s.preferred_source = 'VA_GDX'
      AND s.allocation_source = 'VA_GDX'
      AND s.ledger_treatment = 'EXCLUDE_DUPLICATE';

    IF v_classifications <> 1
       OR v_policies <> 1
       OR v_mappings <> 1
       OR v_valid <> 1 THEN
        RAISE EXCEPTION
            'POSTCHECK FAILED: classifications %, policies %, mappings %, valid %',
            v_classifications, v_policies, v_mappings, v_valid;
    END IF;

    RAISE NOTICE
        'ETL-211N5B POST-MIGRATION CONTROLS PASS';
END
$$;

COMMIT;

\echo ''
\echo 'ETL-211N5B COMPLETE - TRANSACTION COMMITTED'
