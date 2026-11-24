-- ============================================================
-- WCFFBP ETL-210P
-- INDEPENDENT HISTORICAL HIGHWAY POLICY VALIDATION
-- AL 20.205, FY2018-FY2024
--
-- READ ONLY - NO DATABASE WRITES
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-210P - INDEPENDENT HIGHWAY POLICY VALIDATION'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- ============================================================
-- 1. PERSISTED POLICY RECORDS
-- ============================================================

\echo ''
\echo '1. SOURCE POLICY RECORDS'

SELECT
    federal_inflow_source_policy_id,
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    ledger_treatment,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    source_selection_basis
FROM reference.federal_inflow_source_policy
WHERE federal_inflow_source_policy_id IN (21, 59)
ORDER BY valid_from_fiscal_year;


\echo ''
\echo '2. PROGRAM MAPPING RECORDS'

SELECT
    federal_inflow_program_policy_mapping_id,
    federal_inflow_source_policy_id,
    source_system,
    source_program_code,
    resolved_accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    mapping_basis
FROM reference.federal_inflow_program_policy_mapping
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND BTRIM(source_program_code) = '20.205'
ORDER BY valid_from_fiscal_year;


-- ============================================================
-- 2. FISCAL-YEAR COVERAGE
-- ============================================================

\echo ''
\echo '3. FISCAL-YEAR POLICY COVERAGE'

WITH years AS (
    SELECT generate_series(2018, 2024) AS fiscal_year
)
SELECT
    y.fiscal_year,
    COUNT(p.federal_inflow_program_policy_mapping_id)
        AS applicable_mappings,
    STRING_AGG(
        p.federal_inflow_program_policy_mapping_id::text,
        ', ' ORDER BY p.federal_inflow_program_policy_mapping_id
    ) AS mapping_ids,
    STRING_AGG(
        p.resolved_accounting_disposition,
        ', ' ORDER BY p.federal_inflow_program_policy_mapping_id
    ) AS dispositions
FROM years y
LEFT JOIN reference.federal_inflow_program_policy_mapping p
  ON p.source_system = 'USASPENDING_ASSISTANCE'
 AND BTRIM(p.source_program_code) = '20.205'
 AND y.fiscal_year BETWEEN
     COALESCE(p.valid_from_fiscal_year, -9999)
     AND COALESCE(p.valid_through_fiscal_year, 9999)
GROUP BY y.fiscal_year
ORDER BY y.fiscal_year;


-- ============================================================
-- 3. HISTORICAL TRANSACTION COVERAGE
-- ============================================================

\echo ''
\echo '4. HISTORICAL TRANSACTION CLASSIFICATION'

WITH historical AS (
    SELECT
        c.assistance_transaction_id,
        c.action_date_fiscal_year AS fiscal_year,
        c.federal_action_obligation,
        COALESCE(
            NULLIF(BTRIM(c.award_id_fain), ''),
            NULLIF(BTRIM(c.award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger c
    WHERE BTRIM(c.cfda_number) = '20.205'
      AND (
           (c.load_batch_id = 20
            AND c.action_date_fiscal_year = 2018)
        OR (c.load_batch_id = 21
            AND c.action_date_fiscal_year = 2019)
      )
),
classified AS (
    SELECT
        h.*,
        p.federal_inflow_program_policy_mapping_id,
        p.resolved_accounting_disposition,
        (
            SELECT COUNT(*)
            FROM reference.federal_inflow_award_classification a
            WHERE a.source_system = 'USASPENDING_ASSISTANCE'
              AND BTRIM(a.source_program_code) = '20.205'
              AND a.source_award_identifier = h.award_identifier
              AND h.fiscal_year BETWEEN
                  COALESCE(a.valid_from_fiscal_year, -9999)
                  AND COALESCE(a.valid_through_fiscal_year, 9999)
        ) AS award_override_count
    FROM historical h
    LEFT JOIN reference.federal_inflow_program_policy_mapping p
      ON p.source_system = 'USASPENDING_ASSISTANCE'
     AND BTRIM(p.source_program_code) = '20.205'
     AND h.fiscal_year BETWEEN
         COALESCE(p.valid_from_fiscal_year, -9999)
         AND COALESCE(p.valid_through_fiscal_year, 9999)
)
SELECT
    fiscal_year,
    resolved_accounting_disposition,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations,
    COUNT(*) FILTER (
        WHERE award_override_count > 0
    ) AS award_override_matches
FROM classified
GROUP BY fiscal_year, resolved_accounting_disposition
ORDER BY fiscal_year, resolved_accounting_disposition;


-- ============================================================
-- 4. AUTOMATED INDEPENDENT ASSERTIONS
-- ============================================================

\echo ''
\echo '5. AUTOMATED VALIDATION'

DO $$
DECLARE
    v_old_source integer;
    v_new_source integer;
    v_old_mapping integer;
    v_new_mapping integer;
    v_bad_years integer;
    v_bad_links integer;
    v_rows bigint;
    v_distinct bigint;
    v_net numeric;
    v_bad_classification bigint;
    v_award_overrides bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_old_source
    FROM reference.federal_inflow_source_policy
    WHERE federal_inflow_source_policy_id = 21
      AND inflow_family = 'TRANSPORTATION_ASSISTANCE'
      AND inflow_subfamily = 'HIGHWAY_INFRASTRUCTURE'
      AND preferred_source = 'USASPENDING_ASSISTANCE'
      AND accounting_measure = 'NET_FEDERAL_ACTION_OBLIGATION'
      AND ledger_treatment = 'INCLUDE'
      AND methodology_version = 'ANALYSIS-174B-5V-v2'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;

    SELECT COUNT(*)
    INTO v_new_source
    FROM reference.federal_inflow_source_policy
    WHERE federal_inflow_source_policy_id = 59
      AND inflow_family = 'TRANSPORTATION_ASSISTANCE'
      AND inflow_subfamily = 'HIGHWAY_INFRASTRUCTURE'
      AND preferred_source = 'USASPENDING_ASSISTANCE'
      AND accounting_measure = 'NET_FEDERAL_ACTION_OBLIGATION'
      AND ledger_treatment = 'INCLUDE'
      AND methodology_version = 'ANALYSIS-210O-HIGHWAY-HIST-v1'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    SELECT COUNT(*)
    INTO v_old_mapping
    FROM reference.federal_inflow_program_policy_mapping
    WHERE federal_inflow_program_policy_mapping_id = 67
      AND federal_inflow_source_policy_id = 21
      AND source_system = 'USASPENDING_ASSISTANCE'
      AND BTRIM(source_program_code) = '20.205'
      AND resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
      AND methodology_version = 'ANALYSIS-174B-5V-v2'
      AND valid_from_fiscal_year = 2020
      AND valid_through_fiscal_year = 2024;

    SELECT COUNT(*)
    INTO v_new_mapping
    FROM reference.federal_inflow_program_policy_mapping
    WHERE federal_inflow_program_policy_mapping_id = 105
      AND federal_inflow_source_policy_id = 59
      AND source_system = 'USASPENDING_ASSISTANCE'
      AND BTRIM(source_program_code) = '20.205'
      AND resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
      AND methodology_version = 'ANALYSIS-210O-HIGHWAY-HIST-v1'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    WITH years AS (
        SELECT generate_series(2018, 2024) AS fiscal_year
    )
    SELECT COUNT(*)
    INTO v_bad_years
    FROM years y
    WHERE (
        SELECT COUNT(*)
        FROM reference.federal_inflow_program_policy_mapping p
        WHERE p.source_system = 'USASPENDING_ASSISTANCE'
          AND BTRIM(p.source_program_code) = '20.205'
          AND y.fiscal_year BETWEEN
              COALESCE(p.valid_from_fiscal_year, -9999)
              AND COALESCE(p.valid_through_fiscal_year, 9999)
          AND p.resolved_accounting_disposition =
              'INCLUDE_ADDITIVE'
    ) <> 1
    OR (
        SELECT COUNT(*)
        FROM reference.federal_inflow_program_policy_mapping p
        WHERE p.source_system = 'USASPENDING_ASSISTANCE'
          AND BTRIM(p.source_program_code) = '20.205'
          AND y.fiscal_year BETWEEN
              COALESCE(p.valid_from_fiscal_year, -9999)
              AND COALESCE(p.valid_through_fiscal_year, 9999)
    ) <> 1;

    SELECT COUNT(*)
    INTO v_bad_links
    FROM reference.federal_inflow_program_policy_mapping p
    LEFT JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         p.federal_inflow_source_policy_id
    WHERE p.federal_inflow_program_policy_mapping_id IN (67, 105)
      AND (
          s.federal_inflow_source_policy_id IS NULL
          OR s.methodology_version <> p.methodology_version
          OR s.valid_from_fiscal_year <>
             p.valid_from_fiscal_year
          OR s.valid_through_fiscal_year <>
             p.valid_through_fiscal_year
      );

    WITH historical AS (
        SELECT
            c.assistance_transaction_id,
            c.action_date_fiscal_year AS fiscal_year,
            c.federal_action_obligation,
            COALESCE(
                NULLIF(BTRIM(c.award_id_fain), ''),
                NULLIF(BTRIM(c.award_id_uri), '')
            ) AS award_identifier
        FROM analysis.v_certified_assistance_ledger c
        WHERE BTRIM(c.cfda_number) = '20.205'
          AND (
               (c.load_batch_id = 20
                AND c.action_date_fiscal_year = 2018)
            OR (c.load_batch_id = 21
                AND c.action_date_fiscal_year = 2019)
          )
    ),
    classified AS (
        SELECT
            h.*,
            p.resolved_accounting_disposition,
            (
                SELECT COUNT(*)
                FROM reference.federal_inflow_award_classification a
                WHERE a.source_system = 'USASPENDING_ASSISTANCE'
                  AND BTRIM(a.source_program_code) = '20.205'
                  AND a.source_award_identifier = h.award_identifier
                  AND h.fiscal_year BETWEEN
                      COALESCE(a.valid_from_fiscal_year, -9999)
                      AND COALESCE(a.valid_through_fiscal_year, 9999)
            ) AS award_override_count
        FROM historical h
        LEFT JOIN reference.federal_inflow_program_policy_mapping p
          ON p.source_system = 'USASPENDING_ASSISTANCE'
         AND BTRIM(p.source_program_code) = '20.205'
         AND h.fiscal_year BETWEEN
             COALESCE(p.valid_from_fiscal_year, -9999)
             AND COALESCE(p.valid_through_fiscal_year, 9999)
    )
    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),
        COALESCE(SUM(federal_action_obligation), 0),
        COUNT(*) FILTER (
            WHERE resolved_accounting_disposition
                IS DISTINCT FROM 'INCLUDE_ADDITIVE'
        ),
        COUNT(*) FILTER (
            WHERE award_override_count <> 0
        )
    INTO
        v_rows,
        v_distinct,
        v_net,
        v_bad_classification,
        v_award_overrides
    FROM classified;

    IF v_old_source <> 1
       OR v_new_source <> 1
       OR v_old_mapping <> 1
       OR v_new_mapping <> 1
       OR v_bad_years <> 0
       OR v_bad_links <> 0
       OR v_rows <> 4799
       OR v_distinct <> 4799
       OR ROUND(v_net, 2) <> 1451503112.03
       OR v_bad_classification <> 0
       OR v_award_overrides <> 0
    THEN
        RAISE EXCEPTION
            'ETL-210P FAIL: old/new source %/%, old/new mapping %/%, bad years %, bad links %, rows %, distinct %, net %, bad dispositions %, overrides %',
            v_old_source, v_new_source,
            v_old_mapping, v_new_mapping,
            v_bad_years, v_bad_links,
            v_rows, v_distinct, v_net,
            v_bad_classification, v_award_overrides;
    END IF;

    RAISE NOTICE
        'ETL-210P PASS: 4799 historical highway transactions additive; $1451503112.03 net; unique FY2018-FY2024 policy coverage; original policy preserved; zero award overrides';

END $$;

COMMIT;

\echo 'ETL-210P COMPLETE - NO DATABASE WRITES'