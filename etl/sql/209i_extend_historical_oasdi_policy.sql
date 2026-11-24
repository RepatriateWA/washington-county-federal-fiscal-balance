
\pset pager off
\set ON_ERROR_STOP on

\echo '============================================================'
\echo 'ETL-209I - HISTORICAL OASDI OVERLAP POLICY EXTENSION'
\echo 'ANALYSIS-209I-v1 / FY2018-FY2019 ONLY'
\echo '============================================================'

BEGIN;

-- 1. PREFLIGHT: SOURCE, POLICY AND COLLISION CONTROLS

DO $$
DECLARE
    v_count bigint;
    v_amount numeric;
    v_code text;
BEGIN
    IF EXISTS (
        SELECT 1
        FROM reference.federal_inflow_source_policy
        WHERE methodology_version = 'ANALYSIS-209I-v1'
    )
    OR EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_classification
        WHERE methodology_version = 'ANALYSIS-209I-v1'
    )
    OR EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_policy_mapping
        WHERE methodology_version = 'ANALYSIS-209I-v1'
    ) THEN
        RAISE EXCEPTION
            'ETL-209I ABORT: methodology already exists';
    END IF;

    IF (
        SELECT COUNT(*)
        FROM reference.federal_inflow_source_policy
        WHERE inflow_family = 'SOCIAL_SECURITY'
          AND inflow_subfamily = 'OASDI'
          AND methodology_version = 'ANALYSIS-116-v1'
          AND preferred_source = 'SSA'
          AND allocation_source = 'SSA'
          AND ledger_treatment = 'INCLUDE_AFTER_RECONCILIATION'
          AND valid_from_fiscal_year = 2020
          AND valid_through_fiscal_year = 2024
    ) <> 1 THEN
        RAISE EXCEPTION
            'ETL-209I ABORT: original SSA source policy not unique';
    END IF;

    FOREACH v_code IN ARRAY ARRAY[
        '96.001', '96.002', '96.004'
    ]
    LOOP
        IF (
            SELECT COUNT(*)
            FROM reference.federal_inflow_program_policy_mapping
            WHERE source_system = 'USASPENDING_ASSISTANCE'
              AND source_program_code = v_code
              AND resolved_accounting_disposition = 'EXCLUDE_DUPLICATE'
              AND methodology_version = 'ANALYSIS-174B-5L-v1'
              AND valid_from_fiscal_year = 2020
              AND valid_through_fiscal_year = 2024
        ) <> 1 THEN
            RAISE EXCEPTION
                'ETL-209I ABORT: later mapping invalid for %',
                v_code;
        END IF;

        IF (
            SELECT COUNT(*)
            FROM reference.federal_inflow_program_classification
            WHERE source_system = 'USASPENDING_ASSISTANCE'
              AND source_program_code = v_code
              AND valid_from_fiscal_year <= 2020
              AND valid_through_fiscal_year >= 2024
        ) <> 1 THEN
            RAISE EXCEPTION
                'ETL-209I ABORT: original classification not unique for %',
                v_code;
        END IF;
    END LOOP;

    -- Do not permit another mapping to cover either historical year.
    IF EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_policy_mapping
        WHERE source_system = 'USASPENDING_ASSISTANCE'
          AND source_program_code IN (
              '96.001', '96.002', '96.004'
          )
          AND COALESCE(valid_from_fiscal_year, -9999) <= 2019
          AND COALESCE(valid_through_fiscal_year, 9999) >= 2018
    ) THEN
        RAISE EXCEPTION
            'ETL-209I ABORT: overlapping historical mapping exists';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_classification
        WHERE source_system = 'USASPENDING_ASSISTANCE'
          AND source_program_code IN (
              '96.001', '96.002', '96.004'
          )
          AND COALESCE(valid_from_fiscal_year, -9999) <= 2019
          AND COALESCE(valid_through_fiscal_year, 9999) >= 2018
    ) THEN
        RAISE EXCEPTION
            'ETL-209I ABORT: overlapping historical classification exists';
    END IF;

    SELECT
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0)
    INTO v_count, v_amount
    FROM analysis.v_certified_assistance_ledger
    WHERE (
           (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
      AND BTRIM(cfda_number) IN (
          '96.001', '96.002', '96.004'
      );

    IF v_count <> 4938
       OR ROUND(v_amount, 2) <> 45264113835.00
    THEN
        RAISE EXCEPTION
            'ETL-209I ABORT: source control count %, amount %',
            v_count, v_amount;
    END IF;

    IF (
        SELECT COUNT(*)
        FROM ssa.benefit_payments
        WHERE report_year IN (2018, 2019)
          AND benefit_type = 'Total'
    ) <> 78 THEN
        RAISE EXCEPTION
            'ETL-209I ABORT: SSA county total coverage changed';
    END IF;

    IF (
        SELECT COUNT(*)
        FROM (
            SELECT report_year
            FROM ssa.benefit_payments
            WHERE report_year IN (2018, 2019)
              AND benefit_type = 'Total'
            GROUP BY report_year
            HAVING
                (report_year = 2018 AND
                 SUM(annual_benefits_thousands) * 1000
                     = 22964844000)
                OR
                (report_year = 2019 AND
                 SUM(annual_benefits_thousands) * 1000
                     = 24211620000)
        ) verified
    ) <> 2 THEN
        RAISE EXCEPTION
            'ETL-209I ABORT: SSA financial controls changed';
    END IF;

    RAISE NOTICE
        'ETL-209I preflight PASS: 4938 transactions / $45,264,113,835';
END
$$;

-- 2. HISTORICAL SOURCE POLICY
-- Clone the original SSA policy without altering its FY2020-2024 window.

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
    'ETL-209I historical OASDI overlap extension. '
    || 'ETL-209H independently verified SSA county coverage, '
    || 'beneficiary reconciliation and source financial controls '
    || 'for 2018 and 2019. USAspending AL 96.001, 96.002 and '
    || '96.004 represent materially overlapping OASDI benefits '
    || 'and are not independently additive to SSA OASDI. '
    || 'Historical USAspending obligations total '
    || '$45,264,113,835 across 4,938 transactions. '
    || 'SSA December monthly benefits multiplied by twelve '
    || 'are annualized run-rates, not observed federal-fiscal-year '
    || 'cash expenditures. This extension establishes duplicate '
    || 'exclusion, not a final FFY expenditure measurement. '
    || 'SSI AL 96.006 is outside scope.',
    'ANALYSIS-209I-v1',
    2018,
    2019,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM reference.federal_inflow_source_policy
WHERE inflow_family = 'SOCIAL_SECURITY'
  AND inflow_subfamily = 'OASDI'
  AND methodology_version = 'ANALYSIS-116-v1'
  AND valid_from_fiscal_year = 2020
  AND valid_through_fiscal_year = 2024;

-- 3. HISTORICAL PROGRAM CLASSIFICATIONS

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
    'ETL-209I: FY2018-FY2019 historical OASDI overlap '
    || 'extension based on ETL-209H source reconciliation. '
    || 'USAspending obligations are nonadditive to the SSA '
    || 'OASDI benefit universe. Final FFY expenditure '
    || 'measurement is not certified.',
    'ANALYSIS-209I-v1',
    2018,
    2019,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM reference.federal_inflow_program_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code IN (
      '96.001', '96.002', '96.004'
  )
  AND valid_from_fiscal_year <= 2020
  AND valid_through_fiscal_year >= 2024;

-- 4. HISTORICAL PROGRAM-TO-SOURCE POLICY MAPPINGS

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
    m.source_system,
    m.source_program_code,
    p.federal_inflow_source_policy_id,
    'EXCLUDE_DUPLICATE',
    'ETL-209I: historical FY2018-FY2019 OASDI duplicate '
    || 'exclusion, supported by ETL-209H. USAspending '
    || 'transactions remain preserved as provenance. '
    || 'SSA is preferred; final FFY expenditure accounting '
    || 'measure remains subject to separate certification.',
    'ANALYSIS-209I-v1',
    2018,
    2019,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM reference.federal_inflow_program_policy_mapping m
CROSS JOIN reference.federal_inflow_source_policy p
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code IN (
      '96.001', '96.002', '96.004'
  )
  AND m.methodology_version = 'ANALYSIS-174B-5L-v1'
  AND m.valid_from_fiscal_year = 2020
  AND m.valid_through_fiscal_year = 2024
  AND m.resolved_accounting_disposition = 'EXCLUDE_DUPLICATE'
  AND p.methodology_version = 'ANALYSIS-209I-v1'
  AND p.inflow_family = 'SOCIAL_SECURITY'
  AND p.inflow_subfamily = 'OASDI'
  AND p.valid_from_fiscal_year = 2018
  AND p.valid_through_fiscal_year = 2019;

-- 5. VERIFY ALL NEW RECORDS BEFORE COMMIT

DO $$
DECLARE
    v_source bigint;
    v_classes bigint;
    v_mappings bigint;
    v_original bigint;
    v_resolved bigint;
    v_amount numeric;
BEGIN
    SELECT COUNT(*) INTO v_source
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version = 'ANALYSIS-209I-v1'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019
      AND preferred_source = 'SSA'
      AND ledger_treatment = 'INCLUDE_AFTER_RECONCILIATION';

    SELECT COUNT(*) INTO v_classes
    FROM reference.federal_inflow_program_classification
    WHERE methodology_version = 'ANALYSIS-209I-v1'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    SELECT COUNT(*) INTO v_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE methodology_version = 'ANALYSIS-209I-v1'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019
      AND resolved_accounting_disposition = 'EXCLUDE_DUPLICATE';

    SELECT COUNT(*) INTO v_original
    FROM reference.federal_inflow_program_policy_mapping
    WHERE methodology_version = 'ANALYSIS-174B-5L-v1'
      AND source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code IN (
          '96.001', '96.002', '96.004'
      )
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024
      AND resolved_accounting_disposition = 'EXCLUDE_DUPLICATE';

    SELECT
        COUNT(*),
        COALESCE(SUM(s.federal_action_obligation), 0)
    INTO v_resolved, v_amount
    FROM analysis.v_certified_assistance_ledger s
    JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_system = 'USASPENDING_ASSISTANCE'
     AND m.source_program_code = BTRIM(s.cfda_number)
     AND s.action_date_fiscal_year
         BETWEEN m.valid_from_fiscal_year
             AND m.valid_through_fiscal_year
    WHERE (
           (s.load_batch_id = 20
            AND s.action_date_fiscal_year = 2018)
        OR (s.load_batch_id = 21
            AND s.action_date_fiscal_year = 2019)
    )
      AND m.methodology_version = 'ANALYSIS-209I-v1'
      AND m.resolved_accounting_disposition = 'EXCLUDE_DUPLICATE';

    IF v_source <> 1
       OR v_classes <> 3
       OR v_mappings <> 3
       OR v_original <> 3
       OR v_resolved <> 4938
       OR ROUND(v_amount, 2) <> 45264113835.00
    THEN
        RAISE EXCEPTION
            'ETL-209I FAIL: source %, classes %, mappings %, original %, transactions %, amount %',
            v_source, v_classes, v_mappings,
            v_original, v_resolved, v_amount;
    END IF;

    RAISE NOTICE
        'ETL-209I PASS: 1 source policy, 3 classifications, 3 mappings; 4938 historical transactions excluded from duplicate additive accounting';
END
$$;

COMMIT;

\echo 'ETL-209I COMPLETE - HISTORICAL OASDI POLICY COMMITTED'
