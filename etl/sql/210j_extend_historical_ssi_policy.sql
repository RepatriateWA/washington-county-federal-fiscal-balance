-- ============================================================
-- WCFFBP ETL-210J
-- HISTORICAL SSI POLICY EXTENSION
-- AL 96.006, FY2018-FY2019
--
-- WRITES TWO POLICY RECORDS ONLY
-- Requires ETL-210H and ETL-210I PASS
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-210J - HISTORICAL SSI POLICY EXTENSION'
\echo 'FY2018-FY2019'
\echo '============================================================'

BEGIN;

LOCK TABLE
    reference.federal_inflow_source_policy,
    reference.federal_inflow_program_policy_mapping
IN SHARE ROW EXCLUSIVE MODE;

-- 1. PRE-INSERT ASSERTIONS

DO $$
DECLARE
    v_original integer;
    v_conflicts integer;
    v_rows bigint;
    v_distinct bigint;
    v_net numeric;
    v_2018 numeric;
    v_2019 numeric;
    v_awards bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_original
    FROM reference.federal_inflow_program_policy_mapping p
    JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         p.federal_inflow_source_policy_id
    WHERE p.federal_inflow_program_policy_mapping_id = 4
      AND s.federal_inflow_source_policy_id = 11
      AND p.source_system = 'USASPENDING_ASSISTANCE'
      AND p.source_program_code = '96.006'
      AND p.resolved_accounting_disposition =
          'INCLUDE_ADDITIVE'
      AND p.methodology_version = 'ANALYSIS-174B-5L-v1'
      AND p.valid_from_fiscal_year = 2020
      AND p.valid_through_fiscal_year = 2024
      AND s.inflow_family = 'SOCIAL_SECURITY'
      AND s.inflow_subfamily =
          'SUPPLEMENTAL_SECURITY_INCOME'
      AND s.accounting_measure =
          'ANNUAL_SSI_BENEFIT_PAYMENTS'
      AND s.preferred_source =
          'USASPENDING_ASSISTANCE_96.006'
      AND s.ledger_treatment = 'INCLUDE'
      AND s.valid_from_fiscal_year = 2020
      AND s.valid_through_fiscal_year = 2024;

    SELECT COUNT(*)
    INTO v_conflicts
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND BTRIM(source_program_code) = '96.006'
      AND COALESCE(valid_from_fiscal_year, -9999) <= 2019
      AND COALESCE(valid_through_fiscal_year, 9999) >= 2018;

    IF EXISTS (
        SELECT 1
        FROM reference.federal_inflow_source_policy
        WHERE methodology_version = 'ANALYSIS-210J-SSI-HIST-v1'
    ) OR EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_policy_mapping
        WHERE methodology_version = 'ANALYSIS-210J-SSI-HIST-v1'
    ) THEN
        RAISE EXCEPTION
            'ETL-210J: historical methodology already exists';
    END IF;

    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),
        COALESCE(SUM(federal_action_obligation), 0),
        COALESCE(SUM(federal_action_obligation) FILTER (
            WHERE action_date_fiscal_year = 2018
        ), 0),
        COALESCE(SUM(federal_action_obligation) FILTER (
            WHERE action_date_fiscal_year = 2019
        ), 0)
    INTO v_rows, v_distinct, v_net, v_2018, v_2019
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) = '96.006'
      AND (
           (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
      );

    WITH historical AS (
        SELECT
            c.action_date_fiscal_year AS fy,
            COALESCE(
                NULLIF(BTRIM(c.award_id_fain), ''),
                NULLIF(BTRIM(c.award_id_uri), '')
            ) AS award_identifier
        FROM analysis.v_certified_assistance_ledger c
        WHERE BTRIM(c.cfda_number) = '96.006'
          AND (
               (c.load_batch_id = 20
                AND c.action_date_fiscal_year = 2018)
            OR (c.load_batch_id = 21
                AND c.action_date_fiscal_year = 2019)
          )
    )
    SELECT COUNT(a.accounting_disposition)
    INTO v_awards
    FROM historical h
    LEFT JOIN reference.federal_inflow_award_classification a
      ON a.source_system = 'USASPENDING_ASSISTANCE'
     AND BTRIM(a.source_program_code) = '96.006'
     AND a.source_award_identifier = h.award_identifier
     AND h.fy BETWEEN
         COALESCE(a.valid_from_fiscal_year, -9999)
         AND COALESCE(a.valid_through_fiscal_year, 9999);

    IF v_original <> 1
       OR v_conflicts <> 0
       OR v_rows <> 1658
       OR v_distinct <> 1658
       OR ROUND(v_net, 2) <> 2084260846.00
       OR ROUND(v_2018, 2) <> 995804337.00
       OR ROUND(v_2019, 2) <> 1088456509.00
       OR v_awards <> 0
    THEN
        RAISE EXCEPTION
            'ETL-210J preflight FAIL: original %, conflicts %, rows %, distinct %, net %, FY18 %, FY19 %, overrides %',
            v_original, v_conflicts, v_rows, v_distinct,
            v_net, v_2018, v_2019, v_awards;
    END IF;

    RAISE NOTICE 'ETL-210J pre-insert controls PASS';
END $$;

-- 2. CREATE FY2018-FY2019 SOURCE POLICY

\echo ''
\echo '1. INSERT HISTORICAL SSI SOURCE POLICY'

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
    COALESCE(source_selection_basis, '')
      || ' ETL-210J historical extension: FY2018-FY2019.'
      || ' ETL-210H verified 1,658 certified transactions'
      || ' totaling $2,084,260,846.00.'
      || ' SSA is awarding and funding agency.'
      || ' Source identifies aggregate SSI benefits,'
      || ' distinct from the SSA OASDI accounting stream.'
      || ' FY2018: 848 transactions/$995,804,337.00.'
      || ' FY2019: 810 transactions/$1,088,456,509.00.'
      || ' Raw USAspending source linkage is complete.'
      || ' ETL-210I verified no historical program mapping'
      || ' or award-level classification override.'
      || ' Statewide accounting only; county allocation'
      || ' remains uncertified and deferred.'
      || ' No extrapolation or imputation is used.'
      || ' COVID attribution is not inferred from'
      || ' blank historical COVID source fields.',
    'ANALYSIS-210J-SSI-HIST-v1',
    2018,
    2019
FROM reference.federal_inflow_source_policy
WHERE federal_inflow_source_policy_id = 11;

-- 3. CREATE HISTORICAL PROGRAM MAPPING

\echo ''
\echo '2. INSERT HISTORICAL SSI PROGRAM MAPPING'

WITH historical_policy AS (
    SELECT federal_inflow_source_policy_id
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version = 'ANALYSIS-210J-SSI-HIST-v1'
      AND inflow_family = 'SOCIAL_SECURITY'
      AND inflow_subfamily = 'SUPPLEMENTAL_SECURITY_INCOME'
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
    '96.006',
    h.federal_inflow_source_policy_id,
    'INCLUDE_ADDITIVE',
    'ETL-210J historical SSI extension, based on'
      || ' ETL-210H source certification and ETL-210I'
      || ' policy preflight. FY2018-FY2019 net federal'
      || ' action obligations are additive to OASDI.'
      || ' Original FY2020-FY2024 policy unchanged.'
      || ' Washington statewide accounting only;'
      || ' no county allocation authorized.',
    'ANALYSIS-210J-SSI-HIST-v1',
    2018,
    2019
FROM historical_policy h
CROSS JOIN new_id n;

-- 4. POST-INSERT VALIDATION

\echo ''
\echo '3. SSI POLICY COVERAGE FY2018-FY2024'

SELECT
    p.federal_inflow_program_policy_mapping_id AS mapping_id,
    p.federal_inflow_source_policy_id AS source_policy_id,
    p.source_program_code,
    p.resolved_accounting_disposition,
    p.methodology_version,
    p.valid_from_fiscal_year,
    p.valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping p
WHERE p.source_system = 'USASPENDING_ASSISTANCE'
  AND p.source_program_code = '96.006'
ORDER BY p.valid_from_fiscal_year;

DO $$
DECLARE
    v_new_source integer;
    v_new_mapping integer;
    v_bad_links integer;
    v_bad_years integer;
    v_original integer;
BEGIN
    SELECT COUNT(*)
    INTO v_new_source
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version = 'ANALYSIS-210J-SSI-HIST-v1'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    SELECT COUNT(*)
    INTO v_new_mapping
    FROM reference.federal_inflow_program_policy_mapping
    WHERE methodology_version = 'ANALYSIS-210J-SSI-HIST-v1'
      AND source_program_code = '96.006'
      AND resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    SELECT COUNT(*)
    INTO v_bad_links
    FROM reference.federal_inflow_program_policy_mapping p
    LEFT JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         p.federal_inflow_source_policy_id
    WHERE p.methodology_version = 'ANALYSIS-210J-SSI-HIST-v1'
      AND (
          s.federal_inflow_source_policy_id IS NULL
          OR s.methodology_version IS DISTINCT FROM
             'ANALYSIS-210J-SSI-HIST-v1'
          OR s.valid_from_fiscal_year IS DISTINCT FROM 2018
          OR s.valid_through_fiscal_year IS DISTINCT FROM 2019
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
          AND p.source_program_code = '96.006'
          AND y.fy BETWEEN
              COALESCE(p.valid_from_fiscal_year, -9999)
              AND COALESCE(p.valid_through_fiscal_year, 9999)
    ) <> 1;

    SELECT COUNT(*)
    INTO v_original
    FROM reference.federal_inflow_program_policy_mapping
    WHERE federal_inflow_program_policy_mapping_id = 4
      AND federal_inflow_source_policy_id = 11
      AND methodology_version = 'ANALYSIS-174B-5L-v1'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;

    IF v_new_source <> 1
       OR v_new_mapping <> 1
       OR v_bad_links <> 0
       OR v_bad_years <> 0
       OR v_original <> 1
    THEN
        RAISE EXCEPTION
            'ETL-210J FAIL: source %, mapping %, links %, year conflicts %, original %',
            v_new_source, v_new_mapping,
            v_bad_links, v_bad_years, v_original;
    END IF;

    RAISE NOTICE
        'ETL-210J PASS: historical SSI mapping added; FY2018-FY2024 coverage unique; original mapping preserved';
END $$;

COMMIT;

\echo 'ETL-210J COMPLETE - COMMITTED'