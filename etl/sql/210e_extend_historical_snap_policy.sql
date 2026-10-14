-- ============================================================
-- WCFFBP ETL-210E
-- HISTORICAL SNAP POLICY EXTENSION
-- FY2018-FY2019
--
-- WRITES TWO POLICY RECORDS
-- Requires successful ETL-210C and ETL-210D
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-210E - HISTORICAL SNAP POLICY EXTENSION'
\echo 'FY2018-FY2019'
\echo '============================================================'

BEGIN;

-- Serialize policy writers while validating and inserting.
LOCK TABLE
    reference.federal_inflow_source_policy,
    reference.federal_inflow_program_policy_mapping
IN SHARE ROW EXCLUSIVE MODE;

-- ============================================================
-- 1. PRE-INSERT ASSERTIONS
-- ============================================================

DO $$
DECLARE
    v_source_count integer;
    v_mapping_count integer;
    v_conflicts integer;
    v_transactions bigint;
    v_net numeric;
BEGIN

    SELECT COUNT(*)
    INTO v_source_count
    FROM reference.federal_inflow_source_policy
    WHERE federal_inflow_source_policy_id = 20
      AND inflow_family = 'NUTRITION_ASSISTANCE'
      AND inflow_subfamily = 'SNAP_BENEFITS'
      AND accounting_measure =
          'NET_FEDERAL_ACTION_OBLIGATION'
      AND ledger_treatment = 'INCLUDE'
      AND preferred_source = 'USASPENDING_ASSISTANCE'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024
      AND methodology_version = 'ANALYSIS-174B-5S-v1';

    IF v_source_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-210E: original SNAP source policy differs from certified baseline';
    END IF;

    SELECT COUNT(*)
    INTO v_mapping_count
    FROM reference.federal_inflow_program_policy_mapping
    WHERE federal_inflow_program_policy_mapping_id = 65
      AND federal_inflow_source_policy_id = 20
      AND source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '10.551'
      AND resolved_accounting_disposition =
          'INCLUDE_ADDITIVE'
      AND methodology_version = 'ANALYSIS-174B-5S-v1'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;

    IF v_mapping_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-210E: original SNAP mapping differs from certified baseline';
    END IF;

    SELECT COUNT(*)
    INTO v_conflicts
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND BTRIM(source_program_code) = '10.551'
      AND COALESCE(valid_from_fiscal_year, -9999) <= 2019
      AND COALESCE(valid_through_fiscal_year, 9999) >= 2018;

    IF v_conflicts <> 0 THEN
        RAISE EXCEPTION
            'ETL-210E: % overlapping historical SNAP mappings',
            v_conflicts;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM reference.federal_inflow_source_policy
        WHERE methodology_version =
              'ANALYSIS-210E-SNAP-HIST-v1'
    ) OR EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_policy_mapping
        WHERE methodology_version =
              'ANALYSIS-210E-SNAP-HIST-v1'
    ) THEN
        RAISE EXCEPTION
            'ETL-210E: historical methodology version already exists';
    END IF;

    SELECT
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0)
    INTO v_transactions, v_net
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) = '10.551'
      AND (
           (load_batch_id = 20
            AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21
            AND action_date_fiscal_year = 2019)
      );

    IF v_transactions <> 27
       OR ROUND(v_net, 2) <> 2461253053.11
    THEN
        RAISE EXCEPTION
            'ETL-210E: source control mismatch: % rows, % net',
            v_transactions, v_net;
    END IF;

    RAISE NOTICE
        'ETL-210E pre-insert controls PASS';
END $$;

-- ============================================================
-- 2. CREATE HISTORICAL SOURCE POLICY
-- ============================================================

\echo ''
\echo '1. INSERT HISTORICAL SNAP SOURCE POLICY'

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
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    source_selection_basis
      || ' ETL-210E historical extension: FY2018-FY2019'
      || ' certified by ETL-210A through ETL-210D.'
      || ' All 27 transactions have raw Washington'
      || ' recipient and performance-state evidence,'
      || ' USDA/FNS agency attribution, and AL 10.551.'
      || ' Net obligations total $2,461,253,053.11.'
      || ' Principal awards identify multiple recipients;'
      || ' two small negative adjustments have named'
      || ' recipients. Normalized recipient, agency,'
      || ' and performance-place foreign keys are'
      || ' unpopulated for these historical records.'
      || ' Washington statewide accounting is supported;'
      || ' county allocation is not certified.'
      || ' Independent USDA FNS-388/FNS-388A issuance'
      || ' reconciliation remains outstanding.'
      || ' COVID provenance remains separate.',
    'ANALYSIS-210E-SNAP-HIST-v1',
    2018,
    2019
FROM reference.federal_inflow_source_policy
WHERE federal_inflow_source_policy_id = 20;

-- ============================================================
-- 3. CREATE HISTORICAL PROGRAM MAPPING
-- ============================================================

\echo ''
\echo '2. INSERT HISTORICAL SNAP PROGRAM MAPPING'

WITH historical_policy AS (
    SELECT federal_inflow_source_policy_id
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version =
          'ANALYSIS-210E-SNAP-HIST-v1'
      AND inflow_family = 'NUTRITION_ASSISTANCE'
      AND inflow_subfamily = 'SNAP_BENEFITS'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019
),
new_id AS (
    SELECT
        MAX(federal_inflow_program_policy_mapping_id) + 1
            AS mapping_id
    FROM reference.federal_inflow_program_policy_mapping
)
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
SELECT
    n.mapping_id,
    'USASPENDING_ASSISTANCE',
    '10.551',
    h.federal_inflow_source_policy_id,
    'INCLUDE_ADDITIVE',
    'ETL-210E extends the established SNAP benefit'
      || ' accounting policy to FY2018-FY2019,'
      || ' following ETL-210C source certification'
      || ' and ETL-210D policy preflight.'
      || ' Use net federal action obligations.'
      || ' Statewide Washington attribution only;'
      || ' no inferred county distribution.'
      || ' Independent FNS issuance reconciliation'
      || ' remains outstanding.',
    'ANALYSIS-210E-SNAP-HIST-v1',
    2018,
    2019
FROM historical_policy h
CROSS JOIN new_id n;

-- ============================================================
-- 4. POST-INSERT CONTROLS
-- ============================================================

\echo ''
\echo '3. POST-INSERT POLICY COVERAGE'

SELECT
    p.federal_inflow_program_policy_mapping_id,
    p.federal_inflow_source_policy_id,
    p.source_program_code,
    p.resolved_accounting_disposition,
    p.methodology_version,
    p.valid_from_fiscal_year,
    p.valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping p
WHERE p.source_system = 'USASPENDING_ASSISTANCE'
  AND p.source_program_code = '10.551'
ORDER BY p.valid_from_fiscal_year;

DO $$
DECLARE
    v_new_source integer;
    v_new_mapping integer;
    v_bad_years integer;
    v_bad_link integer;
BEGIN

    SELECT COUNT(*)
    INTO v_new_source
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version =
          'ANALYSIS-210E-SNAP-HIST-v1'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    SELECT COUNT(*)
    INTO v_new_mapping
    FROM reference.federal_inflow_program_policy_mapping
    WHERE methodology_version =
          'ANALYSIS-210E-SNAP-HIST-v1'
      AND source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '10.551'
      AND resolved_accounting_disposition =
          'INCLUDE_ADDITIVE'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    SELECT COUNT(*)
    INTO v_bad_link
    FROM reference.federal_inflow_program_policy_mapping p
    LEFT JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         p.federal_inflow_source_policy_id
    WHERE p.methodology_version =
          'ANALYSIS-210E-SNAP-HIST-v1'
      AND (
          s.federal_inflow_source_policy_id IS NULL
          OR s.methodology_version <>
             'ANALYSIS-210E-SNAP-HIST-v1'
          OR s.valid_from_fiscal_year <> 2018
          OR s.valid_through_fiscal_year <> 2019
      );

    WITH years AS (
        SELECT generate_series(2018, 2024) AS fy
    )
    SELECT COUNT(*)
    INTO v_bad_years
    FROM years y
    WHERE (
        SELECT COUNT(*)
        FROM reference.federal_inflow_program_policy_mapping p
        WHERE p.source_system = 'USASPENDING_ASSISTANCE'
          AND p.source_program_code = '10.551'
          AND y.fy BETWEEN
              COALESCE(p.valid_from_fiscal_year, -9999)
              AND COALESCE(p.valid_through_fiscal_year, 9999)
    ) <> 1;

    IF v_new_source <> 1
       OR v_new_mapping <> 1
       OR v_bad_link <> 0
       OR v_bad_years <> 0
    THEN
        RAISE EXCEPTION
            'ETL-210E validation failed: source %, mapping %, link %, year gaps/overlaps %',
            v_new_source, v_new_mapping,
            v_bad_link, v_bad_years;
    END IF;

    RAISE NOTICE
        'ETL-210E PASS: FY2018-FY2024 SNAP coverage unique; original FY2020-FY2024 mapping preserved';
END $$;

COMMIT;

\echo 'ETL-210E COMPLETE - COMMITTED'