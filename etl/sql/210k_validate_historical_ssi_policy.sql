-- ============================================================
-- WCFFBP ETL-210K
-- INDEPENDENT HISTORICAL SSI POLICY VALIDATION
-- AL 96.006, FY2018-FY2024
--
-- READ ONLY - NO DATABASE WRITES
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-210K - HISTORICAL SSI POLICY VALIDATION'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- ============================================================
-- 1. SOURCE POLICY AND MAPPING LINKAGE
-- ============================================================

\echo ''
\echo '1. SSI POLICY LINKAGE'

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
  AND BTRIM(p.source_program_code) = '96.006'
ORDER BY p.valid_from_fiscal_year;


-- ============================================================
-- 2. FISCAL-YEAR COVERAGE
-- ============================================================

\echo ''
\echo '2. SSI POLICY COVERAGE FY2018-FY2024'

WITH years AS (
    SELECT generate_series(2018, 2024) AS fiscal_year
)
SELECT
    y.fiscal_year,
    COUNT(p.federal_inflow_program_policy_mapping_id)
        AS matching_mappings,
    COUNT(*) FILTER (
        WHERE p.resolved_accounting_disposition =
              'INCLUDE_ADDITIVE'
    ) AS additive_mappings,
    MIN(p.federal_inflow_program_policy_mapping_id)
        AS mapping_id
FROM years y
LEFT JOIN reference.federal_inflow_program_policy_mapping p
  ON p.source_system = 'USASPENDING_ASSISTANCE'
 AND BTRIM(p.source_program_code) = '96.006'
 AND y.fiscal_year BETWEEN
     COALESCE(p.valid_from_fiscal_year, -9999)
     AND COALESCE(p.valid_through_fiscal_year, 9999)
GROUP BY y.fiscal_year
ORDER BY y.fiscal_year;


-- ============================================================
-- 3. RECONSTRUCT EFFECTIVE HISTORICAL DISPOSITIONS
-- ============================================================

\echo ''
\echo '3. FY2018-FY2019 EFFECTIVE SSI ACCOUNTING'

WITH historical AS (
    SELECT
        c.assistance_transaction_id,
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        c.federal_action_obligation AS obligation,
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
),
resolved AS (
    SELECT
        h.*,
        p.resolved_accounting_disposition
            AS program_disposition,
        a.accounting_disposition
            AS award_disposition
    FROM historical h
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
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations,
    COUNT(*) FILTER (
        WHERE award_disposition IS NOT NULL
    ) AS award_overrides
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
\echo '4. AUTOMATED VALIDATION CONTROLS'

DO $$
DECLARE
    v_bad_policies integer;
    v_bad_years integer;
    v_rows bigint;
    v_distinct bigint;
    v_net numeric;
    v_2018 numeric;
    v_2019 numeric;
    v_bad_dispositions bigint;
    v_award_overrides bigint;
BEGIN

    -- Both policies must retain their exact identities,
    -- periods, accounting measures and source choices.

    WITH expected AS (
        SELECT *
        FROM (
            VALUES
                (
                    104::bigint,
                    58::bigint,
                    2018,
                    2019,
                    'ANALYSIS-210J-SSI-HIST-v1'
                ),
                (
                    4::bigint,
                    11::bigint,
                    2020,
                    2024,
                    'ANALYSIS-174B-5L-v1'
                )
        ) AS x(
            mapping_id,
            source_policy_id,
            first_fy,
            last_fy,
            methodology
        )
    )
    SELECT COUNT(*)
    INTO v_bad_policies
    FROM expected e
    LEFT JOIN reference.federal_inflow_program_policy_mapping p
      ON p.federal_inflow_program_policy_mapping_id =
         e.mapping_id
    LEFT JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         e.source_policy_id
    WHERE p.federal_inflow_program_policy_mapping_id IS NULL
       OR s.federal_inflow_source_policy_id IS NULL
       OR p.federal_inflow_source_policy_id IS DISTINCT FROM
          e.source_policy_id
       OR p.source_system IS DISTINCT FROM
          'USASPENDING_ASSISTANCE'
       OR p.source_program_code IS DISTINCT FROM '96.006'
       OR p.methodology_version IS DISTINCT FROM
          e.methodology
       OR p.valid_from_fiscal_year IS DISTINCT FROM
          e.first_fy
       OR p.valid_through_fiscal_year IS DISTINCT FROM
          e.last_fy
       OR s.valid_from_fiscal_year IS DISTINCT FROM
          e.first_fy
       OR s.valid_through_fiscal_year IS DISTINCT FROM
          e.last_fy
       OR p.resolved_accounting_disposition IS DISTINCT FROM
          'INCLUDE_ADDITIVE'
       OR s.inflow_family IS DISTINCT FROM
          'SOCIAL_SECURITY'
       OR s.inflow_subfamily IS DISTINCT FROM
          'SUPPLEMENTAL_SECURITY_INCOME'
       OR s.accounting_measure IS DISTINCT FROM
          'ANNUAL_SSI_BENEFIT_PAYMENTS'
       OR s.preferred_source IS DISTINCT FROM
          'USASPENDING_ASSISTANCE_96.006'
       OR s.ledger_treatment IS DISTINCT FROM 'INCLUDE';

    -- Each fiscal year must have exactly one additive
    -- program mapping.

    WITH years AS (
        SELECT generate_series(2018, 2024) AS fiscal_year
    ),
    coverage AS (
        SELECT
            y.fiscal_year,
            COUNT(p.federal_inflow_program_policy_mapping_id)
                AS matching_rows,
            COUNT(*) FILTER (
                WHERE p.resolved_accounting_disposition =
                      'INCLUDE_ADDITIVE'
            ) AS additive_rows
        FROM years y
        LEFT JOIN reference.federal_inflow_program_policy_mapping p
          ON p.source_system = 'USASPENDING_ASSISTANCE'
         AND BTRIM(p.source_program_code) = '96.006'
         AND y.fiscal_year BETWEEN
             COALESCE(p.valid_from_fiscal_year, -9999)
             AND COALESCE(p.valid_through_fiscal_year, 9999)
        GROUP BY y.fiscal_year
    )
    SELECT COUNT(*)
    INTO v_bad_years
    FROM coverage
    WHERE matching_rows <> 1
       OR additive_rows <> 1;

    -- Independently reconstruct the effective accounting
    -- outcome, including any award-level overrides.

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
        WHERE BTRIM(c.cfda_number) = '96.006'
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
            p.resolved_accounting_disposition
                AS program_disposition,
            a.accounting_disposition
                AS award_disposition
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
        COALESCE(SUM(obligation) FILTER (
            WHERE fy = 2018
        ), 0),
        COALESCE(SUM(obligation) FILTER (
            WHERE fy = 2019
        ), 0),
        COUNT(*) FILTER (
            WHERE COALESCE(
                award_disposition,
                program_disposition,
                'UNCLASSIFIED_REVIEW'
            ) <> 'INCLUDE_ADDITIVE'
        ),
        COUNT(*) FILTER (
            WHERE award_disposition IS NOT NULL
        )
    INTO
        v_rows,
        v_distinct,
        v_net,
        v_2018,
        v_2019,
        v_bad_dispositions,
        v_award_overrides
    FROM resolved;

    IF v_bad_policies <> 0
       OR v_bad_years <> 0
       OR v_rows <> 1658
       OR v_distinct <> 1658
       OR ROUND(v_net, 2) <> 2084260846.00
       OR ROUND(v_2018, 2) <> 995804337.00
       OR ROUND(v_2019, 2) <> 1088456509.00
       OR v_bad_dispositions <> 0
       OR v_award_overrides <> 0
    THEN
        RAISE EXCEPTION
            'ETL-210K FAIL: policies %, years %, rows %, distinct %, net %, FY18 %, FY19 %, bad dispositions %, overrides %',
            v_bad_policies,
            v_bad_years,
            v_rows,
            v_distinct,
            v_net,
            v_2018,
            v_2019,
            v_bad_dispositions,
            v_award_overrides;
    END IF;

    RAISE NOTICE
        'ETL-210K PASS: 1658 SSI transactions, $2084260846.00 additive; FY2018-FY2024 coverage valid; zero overrides';

END $$;

COMMIT;

\echo 'ETL-210K COMPLETE - READ ONLY'