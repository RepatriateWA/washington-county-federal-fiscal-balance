-- ============================================================
-- WCFFBP ETL-210O
-- HISTORICAL HIGHWAY ASSISTANCE POLICY EXTENSION
-- AL 20.205, FY2018-FY2019
--
-- WRITES TWO POLICY RECORDS
-- Requires ETL-210M and ETL-210N PASS
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-210O - HISTORICAL HIGHWAY POLICY EXTENSION'
\echo 'FY2018-FY2019'
\echo 'DATABASE-WRITING MIGRATION'
\echo '============================================================'

BEGIN;

LOCK TABLE
    reference.federal_inflow_source_policy,
    reference.federal_inflow_program_policy_mapping
IN SHARE ROW EXCLUSIVE MODE;

-- ============================================================
-- 1. PRE-INSERT ASSERTIONS
-- ============================================================

\echo ''
\echo '1. PRE-INSERT ASSERTIONS'

DO $$
DECLARE
    v_source_count integer;
    v_mapping_count integer;
    v_conflicts integer;
    v_version_conflicts integer;
    v_rows bigint;
    v_distinct bigint;
    v_net numeric;
    v_gross numeric;
    v_missing_raw bigint;
    v_non_wa bigint;
    v_award_overrides bigint;
BEGIN

    -- Original FY2020-FY2024 source policy must be intact.

    SELECT COUNT(*)
    INTO v_source_count
    FROM reference.federal_inflow_source_policy
    WHERE federal_inflow_source_policy_id = 21
      AND inflow_family = 'TRANSPORTATION_ASSISTANCE'
      AND inflow_subfamily = 'HIGHWAY_INFRASTRUCTURE'
      AND accounting_measure =
          'NET_FEDERAL_ACTION_OBLIGATION'
      AND preferred_source = 'USASPENDING_ASSISTANCE'
      AND ledger_treatment = 'INCLUDE'
      AND methodology_version = 'ANALYSIS-174B-5V-v2'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;

    IF v_source_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-210O: original highway source policy mismatch';
    END IF;

    -- Original program mapping must be intact.

    SELECT COUNT(*)
    INTO v_mapping_count
    FROM reference.federal_inflow_program_policy_mapping
    WHERE federal_inflow_program_policy_mapping_id = 67
      AND federal_inflow_source_policy_id = 21
      AND source_system = 'USASPENDING_ASSISTANCE'
      AND BTRIM(source_program_code) = '20.205'
      AND resolved_accounting_disposition =
          'INCLUDE_ADDITIVE'
      AND methodology_version = 'ANALYSIS-174B-5V-v2'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;

    IF v_mapping_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-210O: original highway program mapping mismatch';
    END IF;

    -- Historical mapping must not already exist.

    SELECT COUNT(*)
    INTO v_conflicts
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND BTRIM(source_program_code) = '20.205'
      AND COALESCE(valid_from_fiscal_year, -9999) <= 2019
      AND COALESCE(valid_through_fiscal_year, 9999) >= 2018;

    IF v_conflicts <> 0 THEN
        RAISE EXCEPTION
            'ETL-210O: % conflicting historical mappings',
            v_conflicts;
    END IF;

    SELECT
        (
            SELECT COUNT(*)
            FROM reference.federal_inflow_source_policy
            WHERE methodology_version =
                'ANALYSIS-210O-HIGHWAY-HIST-v1'
        )
        +
        (
            SELECT COUNT(*)
            FROM reference.federal_inflow_program_policy_mapping
            WHERE methodology_version =
                'ANALYSIS-210O-HIGHWAY-HIST-v1'
        )
    INTO v_version_conflicts;

    IF v_version_conflicts <> 0 THEN
        RAISE EXCEPTION
            'ETL-210O: historical methodology version already exists';
    END IF;

    -- Independent transaction and raw-provenance controls.

    SELECT
        COUNT(*),
        COUNT(DISTINCT c.assistance_transaction_id),
        COALESCE(SUM(c.federal_action_obligation), 0),
        COALESCE(SUM(ABS(c.federal_action_obligation)), 0),
        COUNT(*) FILTER (WHERE r.raw_record IS NULL),
        COUNT(*) FILTER (
            WHERE r.raw_record IS NULL
               OR NULLIF(
                   BTRIM(r.raw_record->>'recipient_state_code'),
                   ''
               ) IS DISTINCT FROM 'WA'
        )
    INTO
        v_rows,
        v_distinct,
        v_net,
        v_gross,
        v_missing_raw,
        v_non_wa
    FROM analysis.v_certified_assistance_ledger c
    LEFT JOIN assistance.raw_award_transaction r
      ON r.load_batch_id = c.load_batch_id
     AND r.source_row_number = c.source_row_number
    WHERE BTRIM(c.cfda_number) = '20.205'
      AND (
           (c.load_batch_id = 20
            AND c.action_date_fiscal_year = 2018)
        OR (c.load_batch_id = 21
            AND c.action_date_fiscal_year = 2019)
      );

    IF v_rows <> 4799
       OR v_distinct <> 4799
       OR ROUND(v_net, 2) <> 1451503112.03
       OR ROUND(v_gross, 2) <> 2274783059.83
       OR v_missing_raw <> 0
       OR v_non_wa <> 0
    THEN
        RAISE EXCEPTION
            'ETL-210O source control failure: rows %, distinct %, net %, gross %, missing raw %, non-WA %',
            v_rows, v_distinct, v_net, v_gross,
            v_missing_raw, v_non_wa;
    END IF;

    -- Historical award overrides must remain absent.

    SELECT COUNT(*)
    INTO v_award_overrides
    FROM analysis.v_certified_assistance_ledger c
    JOIN reference.federal_inflow_award_classification a
      ON a.source_system = 'USASPENDING_ASSISTANCE'
     AND BTRIM(a.source_program_code) = '20.205'
     AND a.source_award_identifier =
         COALESCE(
             NULLIF(BTRIM(c.award_id_fain), ''),
             NULLIF(BTRIM(c.award_id_uri), '')
         )
     AND c.action_date_fiscal_year BETWEEN
         COALESCE(a.valid_from_fiscal_year, -9999)
         AND COALESCE(a.valid_through_fiscal_year, 9999)
    WHERE BTRIM(c.cfda_number) = '20.205'
      AND (
           (c.load_batch_id = 20
            AND c.action_date_fiscal_year = 2018)
        OR (c.load_batch_id = 21
            AND c.action_date_fiscal_year = 2019)
      );

    IF v_award_overrides <> 0 THEN
        RAISE EXCEPTION
            'ETL-210O: % unexpected historical award overrides',
            v_award_overrides;
    END IF;

    RAISE NOTICE
        'ETL-210O pre-insert PASS: 4799 transactions, $1451503112.03 net, original policy intact';

END $$;


-- ============================================================
-- 2. CREATE HISTORICAL SOURCE POLICY
-- ============================================================

\echo ''
\echo '2. INSERT HISTORICAL HIGHWAY SOURCE POLICY'

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
      || ' ETL-210O historical extension for FY2018-FY2019.'
      || ' ETL-210M and ETL-210N certified 4,799'
      || ' distinct historical transactions with'
      || ' $1,451,503,112.03 net federal obligations'
      || ' and $2,274,783,059.83 gross absolute'
      || ' obligations. All transactions link to raw'
      || ' source records and identify Washington'
      || ' as recipient state. Performance-state'
      || ' field examined is absent throughout;'
      || ' Washington project-performance geography'
      || ' is not independently established.'
      || ' The source population includes DOT and'
      || ' Interior-administered highway assistance,'
      || ' including tribal transportation activity.'
      || ' Preserve net obligations and deobligations.'
      || ' No county allocation is authorized.'
      || ' Independent reconciliation against any'
      || ' separately incorporated FHWA or other'
      || ' transportation expenditure accounting'
      || ' controls remains outstanding; the absence'
      || ' of declared overlap sources does not'
      || ' independently prove absence of overlap.'
      || ' COVID and other extraordinary-funding'
      || ' provenance remain separate.',
    'ANALYSIS-210O-HIGHWAY-HIST-v1',
    2018,
    2019
FROM reference.federal_inflow_source_policy
WHERE federal_inflow_source_policy_id = 21;


-- ============================================================
-- 3. CREATE HISTORICAL PROGRAM MAPPING
-- ============================================================

\echo ''
\echo '3. INSERT HISTORICAL HIGHWAY PROGRAM MAPPING'

WITH historical_policy AS (
    SELECT federal_inflow_source_policy_id
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version =
          'ANALYSIS-210O-HIGHWAY-HIST-v1'
      AND inflow_family = 'TRANSPORTATION_ASSISTANCE'
      AND inflow_subfamily = 'HIGHWAY_INFRASTRUCTURE'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019
),
new_id AS (
    SELECT
        COALESCE(
            MAX(federal_inflow_program_policy_mapping_id),
            0
        ) + 1 AS mapping_id
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
    '20.205',
    h.federal_inflow_source_policy_id,
    'INCLUDE_ADDITIVE',
    'ETL-210O extends established FY2020-FY2024'
      || ' highway infrastructure policy to'
      || ' FY2018-FY2019, following ETL-210M source'
      || ' certification and ETL-210N preflight.'
      || ' Includes DOT and Interior-administered'
      || ' highway and tribal transportation awards.'
      || ' Uses net federal action obligations.'
      || ' Washington recipient-based statewide'
      || ' accounting only; performance geography'
      || ' and county incidence are not certified.'
      || ' Independent FHWA/transportation source'
      || ' overlap reconciliation remains open.',
    'ANALYSIS-210O-HIGHWAY-HIST-v1',
    2018,
    2019
FROM historical_policy h
CROSS JOIN new_id n;


-- ============================================================
-- 4. POST-INSERT VALIDATION
-- ============================================================

\echo ''
\echo '4. POST-INSERT POLICY COVERAGE'

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
  AND BTRIM(p.source_program_code) = '20.205'
ORDER BY p.valid_from_fiscal_year;


\echo ''
\echo '5. POST-INSERT ASSERTIONS'

DO $$
DECLARE
    v_new_source integer;
    v_new_mapping integer;
    v_bad_links integer;
    v_bad_years integer;
    v_original_source integer;
    v_original_mapping integer;
BEGIN

    SELECT COUNT(*)
    INTO v_new_source
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version =
          'ANALYSIS-210O-HIGHWAY-HIST-v1'
      AND inflow_family = 'TRANSPORTATION_ASSISTANCE'
      AND inflow_subfamily = 'HIGHWAY_INFRASTRUCTURE'
      AND ledger_treatment = 'INCLUDE'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    SELECT COUNT(*)
    INTO v_new_mapping
    FROM reference.federal_inflow_program_policy_mapping
    WHERE methodology_version =
          'ANALYSIS-210O-HIGHWAY-HIST-v1'
      AND source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '20.205'
      AND resolved_accounting_disposition =
          'INCLUDE_ADDITIVE'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    SELECT COUNT(*)
    INTO v_bad_links
    FROM reference.federal_inflow_program_policy_mapping p
    LEFT JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         p.federal_inflow_source_policy_id
    WHERE p.methodology_version =
          'ANALYSIS-210O-HIGHWAY-HIST-v1'
      AND (
          s.federal_inflow_source_policy_id IS NULL
          OR s.methodology_version <>
             'ANALYSIS-210O-HIGHWAY-HIST-v1'
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
          AND BTRIM(p.source_program_code) = '20.205'
          AND y.fy BETWEEN
              COALESCE(p.valid_from_fiscal_year, -9999)
              AND COALESCE(p.valid_through_fiscal_year, 9999)
    ) <> 1;

    SELECT COUNT(*)
    INTO v_original_source
    FROM reference.federal_inflow_source_policy
    WHERE federal_inflow_source_policy_id = 21
      AND methodology_version = 'ANALYSIS-174B-5V-v2'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;

    SELECT COUNT(*)
    INTO v_original_mapping
    FROM reference.federal_inflow_program_policy_mapping
    WHERE federal_inflow_program_policy_mapping_id = 67
      AND federal_inflow_source_policy_id = 21
      AND resolved_accounting_disposition =
          'INCLUDE_ADDITIVE'
      AND methodology_version = 'ANALYSIS-174B-5V-v2'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;

    IF v_new_source <> 1
       OR v_new_mapping <> 1
       OR v_bad_links <> 0
       OR v_bad_years <> 0
       OR v_original_source <> 1
       OR v_original_mapping <> 1
    THEN
        RAISE EXCEPTION
            'ETL-210O FAIL: new source %, new mapping %, bad links %, bad years %, original source %, original mapping %',
            v_new_source,
            v_new_mapping,
            v_bad_links,
            v_bad_years,
            v_original_source,
            v_original_mapping;
    END IF;

    RAISE NOTICE
        'ETL-210O PASS: FY2018-FY2024 highway coverage unique; historical additive policy inserted; original FY2020-FY2024 policy preserved';

END $$;

COMMIT;

\echo 'ETL-210O COMPLETE - COMMITTED'