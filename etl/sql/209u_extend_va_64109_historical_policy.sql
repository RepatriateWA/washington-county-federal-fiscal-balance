-- ============================================================
-- WCFFBP ETL-209U
-- HISTORICAL VA AL 64.109 OVERLAP POLICY: FY2018-FY2019
-- Methodology: ANALYSIS-209U-v1
--
-- Preferred accounting source: VA_GDX
-- USAspending treatment: EXCLUDE_DUPLICATE
--
-- Single-use migration; transaction rolls back on failure.
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

BEGIN;

-- ============================================================
-- 1. PRE-MIGRATION HARD CONTROLS
-- ============================================================

DO $$
DECLARE
    v_count bigint;
    v_amount numeric;
    v_bad bigint;
BEGIN

    -- Prevent repeated execution.
    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version = 'ANALYSIS-209U-v1';

    IF v_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-209U already has source-policy records';
    END IF;

    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_program_policy_mapping
    WHERE methodology_version = 'ANALYSIS-209U-v1';

    IF v_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-209U already has mapping records';
    END IF;

    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_program_classification
    WHERE methodology_version = 'ANALYSIS-209U-v1';

    IF v_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-209U already has classification records';
    END IF;

    -- Historical policy windows must be unoccupied.
    SELECT COUNT(*)
    INTO v_bad
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '64.109'
      AND COALESCE(valid_from_fiscal_year, -9999) <= 2019
      AND COALESCE(valid_through_fiscal_year, 9999) >= 2018;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'ETL-209U historical program-policy collision';
    END IF;

    SELECT COUNT(*)
    INTO v_bad
    FROM reference.federal_inflow_award_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '64.109'
      AND COALESCE(valid_from_fiscal_year, -9999) <= 2019
      AND COALESCE(valid_through_fiscal_year, 9999) >= 2018;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'ETL-209U historical award-policy collision';
    END IF;

    -- Original FY2020-FY2024 source policy must be intact.
    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_source_policy
    WHERE federal_inflow_source_policy_id = 16
      AND methodology_version = 'ANALYSIS-174B-5N-v1'
      AND preferred_source = 'VA_GDX'
      AND ledger_treatment = 'EXCLUDE_DUPLICATE'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;

    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-209U original VA source policy not intact';
    END IF;

    -- Original program classification must be intact.
    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_program_classification
    WHERE federal_inflow_program_classification_id = 49
      AND source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '64.109'
      AND methodology_version = 'ANALYSIS-116-v1'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2025;

    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-209U original VA program classification not intact';
    END IF;

    -- Historical USAspending source control.
    SELECT
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0)
    INTO v_count, v_amount
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) = '64.109'
      AND (
          (load_batch_id = 20
           AND action_date_fiscal_year = 2018)
          OR
          (load_batch_id = 21
           AND action_date_fiscal_year = 2019)
      );

    IF v_count <> 929
       OR ROUND(v_amount, 2) <> 4384945713.00 THEN
        RAISE EXCEPTION
            'ETL-209U source mismatch: rows %, amount %',
            v_count, v_amount;
    END IF;

    -- Independent GDX accounting controls.
    SELECT COUNT(*)
    INTO v_bad
    FROM (
        SELECT
            e.fiscal_year,
            COUNT(*) FILTER (
                WHERE c.aggregation_role = 'CONTROL_TOTAL'
            ) AS control_rows,
            COUNT(*) FILTER (
                WHERE c.aggregation_role = 'COMPONENT'
            ) AS component_rows,
            COALESCE(SUM(e.expenditure_amount) FILTER (
                WHERE c.aggregation_role = 'COMPONENT'
            ), 0)
            -
            COALESCE(SUM(e.expenditure_amount) FILTER (
                WHERE c.aggregation_role = 'CONTROL_TOTAL'
            ), 0) AS difference
        FROM va.gdx_county_expenditure e
        JOIN va.gdx_expenditure_category c
          ON c.gdx_category_id = e.gdx_category_id
        WHERE e.fiscal_year IN (2018, 2019)
        GROUP BY e.fiscal_year
    ) q
    WHERE q.control_rows <> 39
       OR q.component_rows <> 273
       OR ROUND(q.difference, 2) <> 0;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'ETL-209U GDX reconciliation failed';
    END IF;

    RAISE NOTICE
        'ETL-209U PRE-MIGRATION CONTROLS PASS';

END $$;


-- ============================================================
-- 2. HISTORICAL PROGRAM CLASSIFICATION
-- ============================================================

INSERT INTO reference.federal_inflow_program_classification
(
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
VALUES
(
    'USASPENDING_ASSISTANCE',
    '64.109',
    'VETERANS COMPENSATION FOR SERVICE-CONNECTED DISABILITY',
    'VETERANS',
    'VETERANS_PROGRAM',
    'KNOWN_OVERLAP',
    false,
    false,
    'Historical FY2018-FY2019 extension of ANALYSIS-116-v1. '
    || 'Program identity is unchanged. VA GDX contains '
    || 'Compensation & Pension expenditures for all 39 '
    || 'Washington counties. Legacy GDX component totals '
    || 'reconcile exactly to annual expenditure controls. '
    || 'Accounting disposition is governed separately '
    || 'by ANALYSIS-209U-v1 source policy and mapping.',
    'ANALYSIS-209U-v1',
    2018,
    2019
);


-- ============================================================
-- 3. HISTORICAL VA GDX SOURCE POLICY
-- ============================================================

INSERT INTO reference.federal_inflow_source_policy
(
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
VALUES
(
    'VETERANS_AFFAIRS',
    'VA_GDX_ASSISTANCE_OVERLAP',
    'VA expenditures',
    'VA_GDX',
    'VA_GDX',
    ARRAY['USASPENDING_ASSISTANCE']::text[],
    'EXCLUDE_DUPLICATE',
    'Historical FY2018-FY2019 extension of '
    || 'ANALYSIS-174B-5N-v1 for Assistance Listing 64.109. '
    || 'Official VA GDX Compensation & Pension expenditures '
    || 'are present for all 39 Washington counties. '
    || 'The legacy category structure matches FY2020 '
    || 'and component expenditures reconcile exactly '
    || 'to annual GDX control totals. USAspending '
    || 'federal action obligations are retained for '
    || 'transaction provenance, not added as a second '
    || 'expenditure stream. Obligations and expenditures '
    || 'are distinct accounting measures. '
    || 'No claim of dollar-for-dollar equality or '
    || 'independent county attribution from USAspending '
    || 'is made.',
    'ANALYSIS-209U-v1',
    2018,
    2019
);


-- ============================================================
-- 4. HISTORICAL PROGRAM-POLICY MAPPING
-- ============================================================

INSERT INTO reference.federal_inflow_program_policy_mapping
(
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
SELECT
    nextval(
        'reference.federal_inflow_program_policy_federal_inflow_program_policy_seq'
    ),
    'USASPENDING_ASSISTANCE',
    '64.109',
    p.federal_inflow_source_policy_id,
    'EXCLUDE_DUPLICATE',
    'FY2018-FY2019 historical VA GDX overlap '
    || 'reconciliation under ANALYSIS-209U-v1. '
    || 'VA GDX is the preferred expenditure and '
    || 'county allocation source. USAspending '
    || 'obligations are nonadditive provenance.',
    'ANALYSIS-209U-v1',
    2018,
    2019
FROM reference.federal_inflow_source_policy p
WHERE p.methodology_version = 'ANALYSIS-209U-v1'
  AND p.preferred_source = 'VA_GDX'
  AND p.valid_from_fiscal_year = 2018
  AND p.valid_through_fiscal_year = 2019;


-- ============================================================
-- 5. POST-INSERT HARD CONTROLS
-- ============================================================

DO $$
DECLARE
    v_count bigint;
    v_rows bigint;
    v_amount numeric;
    v_bad bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_program_classification
    WHERE methodology_version = 'ANALYSIS-209U-v1';

    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-209U classification insertion failed';
    END IF;

    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version = 'ANALYSIS-209U-v1';

    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-209U source policy insertion failed';
    END IF;

    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_program_policy_mapping
    WHERE methodology_version = 'ANALYSIS-209U-v1'
      AND resolved_accounting_disposition =
          'EXCLUDE_DUPLICATE';

    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-209U mapping insertion failed';
    END IF;

    -- Each historical transaction must resolve exactly once.
    WITH historical AS (
        SELECT
            c.assistance_transaction_id,
            c.action_date_fiscal_year AS fiscal_year,
            c.federal_action_obligation
        FROM analysis.v_certified_assistance_ledger c
        WHERE BTRIM(c.cfda_number) = '64.109'
          AND (
              (c.load_batch_id = 20
               AND c.action_date_fiscal_year = 2018)
              OR
              (c.load_batch_id = 21
               AND c.action_date_fiscal_year = 2019)
          )
    ),
    resolved AS (
        SELECT
            h.assistance_transaction_id,
            h.federal_action_obligation,
            COUNT(m.federal_inflow_program_policy_mapping_id)
                AS matching_policies,
            COUNT(*) FILTER (
                WHERE m.resolved_accounting_disposition =
                    'EXCLUDE_DUPLICATE'
            ) AS exclusion_matches
        FROM historical h
        LEFT JOIN reference.federal_inflow_program_policy_mapping m
          ON m.source_system = 'USASPENDING_ASSISTANCE'
         AND m.source_program_code = '64.109'
         AND h.fiscal_year BETWEEN
             COALESCE(m.valid_from_fiscal_year, -9999)
             AND
             COALESCE(m.valid_through_fiscal_year, 9999)
        GROUP BY
            h.assistance_transaction_id,
            h.federal_action_obligation
    )
    SELECT
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0),
        COUNT(*) FILTER (
            WHERE matching_policies <> 1
               OR exclusion_matches <> 1
        )
    INTO v_rows, v_amount, v_bad
    FROM resolved;

    IF v_rows <> 929
       OR ROUND(v_amount, 2) <> 4384945713.00
       OR v_bad <> 0 THEN
        RAISE EXCEPTION
            'ETL-209U effective resolution failed: rows %, amount %, bad %',
            v_rows, v_amount, v_bad;
    END IF;

    RAISE NOTICE
        'ETL-209U CERTIFICATION PASS: 929 transactions, $4384945713.00 nonadditive';

END $$;

COMMIT;

\echo 'ETL-209U COMPLETE'