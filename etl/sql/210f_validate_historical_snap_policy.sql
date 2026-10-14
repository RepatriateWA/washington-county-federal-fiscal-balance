-- ============================================================
-- WCFFBP ETL-210F
-- INDEPENDENT HISTORICAL SNAP POLICY VALIDATION
-- FY2018-FY2024
--
-- READ ONLY - NO DATABASE WRITES
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-210F - HISTORICAL SNAP POLICY VALIDATION'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- ============================================================
-- 1. SOURCE POLICY AND PROGRAM MAPPING LINKAGE
-- ============================================================

\echo ''
\echo '1. SNAP POLICY LINKAGE'

SELECT
    p.federal_inflow_program_policy_mapping_id AS mapping_id,
    s.federal_inflow_source_policy_id AS source_policy_id,
    p.valid_from_fiscal_year AS mapping_from,
    p.valid_through_fiscal_year AS mapping_through,
    s.valid_from_fiscal_year AS source_from,
    s.valid_through_fiscal_year AS source_through,
    p.resolved_accounting_disposition,
    s.ledger_treatment,
    s.accounting_measure,
    s.preferred_source,
    p.methodology_version
FROM reference.federal_inflow_program_policy_mapping p
JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     p.federal_inflow_source_policy_id
WHERE p.source_system = 'USASPENDING_ASSISTANCE'
  AND p.source_program_code = '10.551'
ORDER BY p.valid_from_fiscal_year;


-- ============================================================
-- 2. FISCAL-YEAR COVERAGE AND COLLISION CHECK
-- ============================================================

\echo ''
\echo '2. FISCAL-YEAR POLICY COVERAGE'

WITH fiscal_years AS (
    SELECT generate_series(2018, 2024) AS fiscal_year
)
SELECT
    y.fiscal_year,
    COUNT(p.federal_inflow_program_policy_mapping_id)
        AS matching_mappings,
    MIN(p.federal_inflow_program_policy_mapping_id)
        AS mapping_id,
    MIN(p.resolved_accounting_disposition)
        AS disposition
FROM fiscal_years y
LEFT JOIN reference.federal_inflow_program_policy_mapping p
  ON p.source_system = 'USASPENDING_ASSISTANCE'
 AND p.source_program_code = '10.551'
 AND y.fiscal_year BETWEEN
     COALESCE(p.valid_from_fiscal_year, -9999)
     AND COALESCE(p.valid_through_fiscal_year, 9999)
GROUP BY y.fiscal_year
ORDER BY y.fiscal_year;


-- ============================================================
-- 3. RECONSTRUCT HISTORICAL TRANSACTION DISPOSITIONS
-- ============================================================

\echo ''
\echo '3. FY2018-FY2019 EFFECTIVE ACCOUNTING'

WITH historical AS (
    SELECT
        c.assistance_transaction_id,
        c.action_date_fiscal_year AS fiscal_year,
        c.federal_action_obligation AS obligation,
        BTRIM(c.cfda_number) AS program_code,
        COALESCE(
            NULLIF(BTRIM(c.award_id_fain), ''),
            NULLIF(BTRIM(c.award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger c
    WHERE
        (c.load_batch_id = 20
         AND c.action_date_fiscal_year = 2018)
        OR
        (c.load_batch_id = 21
         AND c.action_date_fiscal_year = 2019)
),
snap AS (
    SELECT *
    FROM historical
    WHERE program_code = '10.551'
),
resolved AS (
    SELECT
        h.*,
        p.resolved_accounting_disposition
            AS program_disposition,
        a.accounting_disposition
            AS award_disposition
    FROM snap h
    LEFT JOIN reference.federal_inflow_program_policy_mapping p
      ON p.source_system = 'USASPENDING_ASSISTANCE'
     AND p.source_program_code = h.program_code
     AND h.fiscal_year BETWEEN
         COALESCE(p.valid_from_fiscal_year, -9999)
         AND COALESCE(p.valid_through_fiscal_year, 9999)
    LEFT JOIN reference.federal_inflow_award_classification a
      ON a.source_system = 'USASPENDING_ASSISTANCE'
     AND a.source_program_code = h.program_code
     AND a.source_award_identifier = h.award_identifier
     AND h.fiscal_year BETWEEN
         COALESCE(a.valid_from_fiscal_year, -9999)
         AND COALESCE(a.valid_through_fiscal_year, 9999)
)
SELECT
    fiscal_year,
    COALESCE(
        award_disposition,
        program_disposition,
        'UNCLASSIFIED_REVIEW'
    ) AS effective_disposition,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations
FROM resolved
GROUP BY
    fiscal_year,
    COALESCE(
        award_disposition,
        program_disposition,
        'UNCLASSIFIED_REVIEW'
    )
ORDER BY fiscal_year, effective_disposition;


-- ============================================================
-- 4. AUTOMATED HARD CONTROLS
-- ============================================================

\echo ''
\echo '4. AUTOMATED VALIDATION'

DO $$
DECLARE
    v_bad_years integer;
    v_bad_policies integer;
    v_bad_transactions integer;
    v_rows bigint;
    v_distinct bigint;
    v_net numeric;
    v_2018 numeric;
    v_2019 numeric;
BEGIN

    -- Exactly one additive program mapping per fiscal year.

    WITH years AS (
        SELECT generate_series(2018, 2024) AS fy
    ),
    coverage AS (
        SELECT
            y.fy,
            COUNT(p.federal_inflow_program_policy_mapping_id)
                AS matching_rows,
            COUNT(*) FILTER (
                WHERE p.resolved_accounting_disposition =
                      'INCLUDE_ADDITIVE'
            ) AS additive_rows
        FROM years y
        LEFT JOIN reference.federal_inflow_program_policy_mapping p
          ON p.source_system = 'USASPENDING_ASSISTANCE'
         AND p.source_program_code = '10.551'
         AND y.fy BETWEEN
             COALESCE(p.valid_from_fiscal_year, -9999)
             AND COALESCE(p.valid_through_fiscal_year, 9999)
        GROUP BY y.fy
    )
    SELECT COUNT(*)
    INTO v_bad_years
    FROM coverage
    WHERE matching_rows <> 1
       OR additive_rows <> 1;

    -- Exact original and historical policy identities.

    SELECT COUNT(*)
    INTO v_bad_policies
    FROM (
        VALUES
            (103::bigint, 57::bigint, 2018, 2019,
             'ANALYSIS-210E-SNAP-HIST-v1'),
            (65::bigint, 20::bigint, 2020, 2024,
             'ANALYSIS-174B-5S-v1')
    ) expected(
        mapping_id,
        source_policy_id,
        first_fy,
        last_fy,
        methodology
    )
    LEFT JOIN reference.federal_inflow_program_policy_mapping p
      ON p.federal_inflow_program_policy_mapping_id =
         expected.mapping_id
    LEFT JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         expected.source_policy_id
    WHERE p.federal_inflow_program_policy_mapping_id IS NULL
       OR s.federal_inflow_source_policy_id IS NULL
       OR p.federal_inflow_source_policy_id IS DISTINCT FROM
          expected.source_policy_id
       OR p.valid_from_fiscal_year IS DISTINCT FROM
          expected.first_fy
       OR p.valid_through_fiscal_year IS DISTINCT FROM
          expected.last_fy
       OR s.valid_from_fiscal_year IS DISTINCT FROM
          expected.first_fy
       OR s.valid_through_fiscal_year IS DISTINCT FROM
          expected.last_fy
       OR p.methodology_version IS DISTINCT FROM
          expected.methodology
       OR s.methodology_version IS DISTINCT FROM
          expected.methodology
       OR p.resolved_accounting_disposition IS DISTINCT FROM
          'INCLUDE_ADDITIVE'
       OR s.ledger_treatment IS DISTINCT FROM 'INCLUDE'
       OR s.accounting_measure IS DISTINCT FROM
          'NET_FEDERAL_ACTION_OBLIGATION'
       OR s.preferred_source IS DISTINCT FROM
          'USASPENDING_ASSISTANCE';

    -- Independently validate historical transaction outcomes.

    WITH historical AS (
        SELECT
            c.assistance_transaction_id,
            c.action_date_fiscal_year AS fy,
            c.federal_action_obligation AS obligation,
            BTRIM(c.cfda_number) AS program_code,
            COALESCE(
                NULLIF(BTRIM(c.award_id_fain), ''),
                NULLIF(BTRIM(c.award_id_uri), '')
            ) AS award_identifier
        FROM analysis.v_certified_assistance_ledger c
        WHERE BTRIM(c.cfda_number) = '10.551'
          AND (
               (c.load_batch_id = 20
                AND c.action_date_fiscal_year = 2018)
            OR (c.load_batch_id = 21
                AND c.action_date_fiscal_year = 2019)
          )
    ),
    resolved AS (
        SELECT
            h.*,
            COALESCE(
                a.accounting_disposition,
                p.resolved_accounting_disposition,
                'UNCLASSIFIED_REVIEW'
            ) AS effective_disposition
        FROM historical h
        LEFT JOIN reference.federal_inflow_program_policy_mapping p
          ON p.source_system = 'USASPENDING_ASSISTANCE'
         AND p.source_program_code = h.program_code
         AND h.fy BETWEEN
             COALESCE(p.valid_from_fiscal_year, -9999)
             AND COALESCE(p.valid_through_fiscal_year, 9999)
        LEFT JOIN reference.federal_inflow_award_classification a
          ON a.source_system = 'USASPENDING_ASSISTANCE'
         AND a.source_program_code = h.program_code
         AND a.source_award_identifier = h.award_identifier
         AND h.fy BETWEEN
             COALESCE(a.valid_from_fiscal_year, -9999)
             AND COALESCE(a.valid_through_fiscal_year, 9999)
    )
    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),
        COALESCE(SUM(obligation), 0),
        COALESCE(SUM(obligation) FILTER (WHERE fy = 2018), 0),
        COALESCE(SUM(obligation) FILTER (WHERE fy = 2019), 0),
        COUNT(*) FILTER (
            WHERE effective_disposition <> 'INCLUDE_ADDITIVE'
        )
    INTO
        v_rows,
        v_distinct,
        v_net,
        v_2018,
        v_2019,
        v_bad_transactions
    FROM resolved;

    IF v_bad_years <> 0
       OR v_bad_policies <> 0
       OR v_rows <> 27
       OR v_distinct <> 27
       OR ROUND(v_net, 2) <> 2461253053.11
       OR ROUND(v_2018, 2) <> 1267951496.84
       OR ROUND(v_2019, 2) <> 1193301556.27
       OR v_bad_transactions <> 0
    THEN
        RAISE EXCEPTION
            'ETL-210F FAIL: years %, policies %, rows %, distinct %, net %, FY18 %, FY19 %, bad dispositions %',
            v_bad_years,
            v_bad_policies,
            v_rows,
            v_distinct,
            v_net,
            v_2018,
            v_2019,
            v_bad_transactions;
    END IF;

    RAISE NOTICE
        'ETL-210F PASS: 27 SNAP transactions, $2461253053.11 additive; FY2018-FY2024 policy coverage valid';
END $$;

COMMIT;

\echo 'ETL-210F COMPLETE - READ ONLY'