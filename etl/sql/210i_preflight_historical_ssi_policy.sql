-- ============================================================
-- WCFFBP ETL-210I
-- HISTORICAL SSI POLICY PREFLIGHT
-- AL 96.006, FY2018-FY2019
--
-- READ ONLY - NO DATABASE WRITES
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-210I - HISTORICAL SSI POLICY PREFLIGHT'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- ============================================================
-- 1. EXISTING SSI SOURCE POLICY
-- ============================================================

\echo ''
\echo '1. EXISTING SSI SOURCE POLICY'

SELECT
    p.federal_inflow_program_policy_mapping_id AS mapping_id,
    s.federal_inflow_source_policy_id AS source_policy_id,
    p.source_program_code,
    p.resolved_accounting_disposition,
    p.methodology_version,
    p.valid_from_fiscal_year AS mapping_from,
    p.valid_through_fiscal_year AS mapping_through,
    s.inflow_family,
    s.inflow_subfamily,
    s.accounting_measure,
    s.preferred_source,
    s.ledger_treatment,
    s.valid_from_fiscal_year AS source_from,
    s.valid_through_fiscal_year AS source_through
FROM reference.federal_inflow_program_policy_mapping p
JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     p.federal_inflow_source_policy_id
WHERE p.source_system = 'USASPENDING_ASSISTANCE'
  AND BTRIM(p.source_program_code) = '96.006'
ORDER BY p.valid_from_fiscal_year;


-- ============================================================
-- 2. POLICY COVERAGE, FY2018-FY2024
-- ============================================================

\echo ''
\echo '2. SSI POLICY COVERAGE BY YEAR'

WITH years AS (
    SELECT generate_series(2018, 2024) AS fiscal_year
)
SELECT
    y.fiscal_year,
    COUNT(p.federal_inflow_program_policy_mapping_id)
        AS matching_mappings,
    MIN(p.resolved_accounting_disposition)
        AS disposition,
    MIN(p.methodology_version)
        AS methodology_version
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
-- 3. HISTORICAL SSI TRANSACTION PROFILE
-- ============================================================

\echo ''
\echo '3. HISTORICAL SSI TRANSACTION CONTROLS'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations,
    COUNT(*) FILTER (
        WHERE federal_action_obligation < 0
    ) AS negative_transactions,
    COUNT(*) FILTER (
        WHERE federal_action_obligation = 0
    ) AS zero_transactions
FROM analysis.v_certified_assistance_ledger
WHERE BTRIM(cfda_number) = '96.006'
  AND (
       (load_batch_id = 20
        AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21
        AND action_date_fiscal_year = 2019)
  )
GROUP BY action_date_fiscal_year
ORDER BY fiscal_year;


-- ============================================================
-- 4. HISTORICAL AWARD-LEVEL OVERRIDE SEARCH
-- ============================================================

\echo ''
\echo '4. HISTORICAL SSI AWARD CLASSIFICATIONS'

WITH historical AS (
    SELECT
        c.action_date_fiscal_year AS fiscal_year,
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
SELECT
    h.fiscal_year,
    COUNT(*) AS transactions,
    COUNT(a.accounting_disposition)
        AS award_classification_matches,
    COUNT(*) FILTER (
        WHERE h.award_identifier IS NULL
    ) AS missing_award_identifiers
FROM historical h
LEFT JOIN reference.federal_inflow_award_classification a
  ON a.source_system = 'USASPENDING_ASSISTANCE'
 AND BTRIM(a.source_program_code) = '96.006'
 AND a.source_award_identifier = h.award_identifier
 AND h.fiscal_year BETWEEN
     COALESCE(a.valid_from_fiscal_year, -9999)
     AND COALESCE(a.valid_through_fiscal_year, 9999)
GROUP BY h.fiscal_year
ORDER BY h.fiscal_year;


-- ============================================================
-- 5. SSA SOURCE-POLICY OVERLAP INVENTORY
-- ============================================================

\echo ''
\echo '5. SSA SOURCE-POLICY INVENTORY'

SELECT
    federal_inflow_source_policy_id,
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    ledger_treatment,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE inflow_family = 'SOCIAL_SECURITY'
   OR inflow_subfamily ILIKE '%SSI%'
   OR inflow_subfamily ILIKE '%OASDI%'
   OR preferred_source ILIKE '%SSA%'
ORDER BY
    inflow_family,
    inflow_subfamily,
    valid_from_fiscal_year;


-- ============================================================
-- 6. AUTOMATED HARD CONTROLS
-- ============================================================

\echo ''
\echo '6. AUTOMATED PREFLIGHT CONTROLS'

DO $$
DECLARE
    v_original_policy integer;
    v_historical_mappings integer;
    v_bad_years integer;
    v_rows bigint;
    v_distinct bigint;
    v_net numeric;
    v_2018 numeric;
    v_2019 numeric;
    v_award_matches bigint;
    v_missing_awards bigint;
BEGIN

    -- Preserve the established FY2020-FY2024 SSI policy.

    SELECT COUNT(*)
    INTO v_original_policy
    FROM reference.federal_inflow_program_policy_mapping p
    JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         p.federal_inflow_source_policy_id
    WHERE p.federal_inflow_program_policy_mapping_id = 4
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

    -- No existing mapping may overlap FY2018-FY2019.

    SELECT COUNT(*)
    INTO v_historical_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND BTRIM(source_program_code) = '96.006'
      AND COALESCE(valid_from_fiscal_year, -9999) <= 2019
      AND COALESCE(valid_through_fiscal_year, 9999) >= 2018;

    -- FY2020-FY2024 must each have exactly one mapping.

    WITH years AS (
        SELECT generate_series(2020, 2024) AS fiscal_year
    )
    SELECT COUNT(*)
    INTO v_bad_years
    FROM years y
    WHERE (
        SELECT COUNT(*)
        FROM reference.federal_inflow_program_policy_mapping p
        WHERE p.source_system = 'USASPENDING_ASSISTANCE'
          AND BTRIM(p.source_program_code) = '96.006'
          AND y.fiscal_year BETWEEN
              COALESCE(p.valid_from_fiscal_year, -9999)
              AND COALESCE(p.valid_through_fiscal_year, 9999)
    ) <> 1;

    -- Independent historical source totals.

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
    INTO
        v_rows,
        v_distinct,
        v_net,
        v_2018,
        v_2019
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) = '96.006'
      AND (
           (load_batch_id = 20
            AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21
            AND action_date_fiscal_year = 2019)
      );

    -- Award overrides must not silently alter classification.

    WITH historical AS (
        SELECT
            c.action_date_fiscal_year AS fiscal_year,
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
    SELECT
        COUNT(a.accounting_disposition),
        COUNT(*) FILTER (
            WHERE h.award_identifier IS NULL
        )
    INTO v_award_matches, v_missing_awards
    FROM historical h
    LEFT JOIN reference.federal_inflow_award_classification a
      ON a.source_system = 'USASPENDING_ASSISTANCE'
     AND BTRIM(a.source_program_code) = '96.006'
     AND a.source_award_identifier = h.award_identifier
     AND h.fiscal_year BETWEEN
         COALESCE(a.valid_from_fiscal_year, -9999)
         AND COALESCE(a.valid_through_fiscal_year, 9999);

    IF v_original_policy <> 1
       OR v_historical_mappings <> 0
       OR v_bad_years <> 0
       OR v_rows <> 1658
       OR v_distinct <> 1658
       OR ROUND(v_net, 2) <> 2084260846.00
       OR ROUND(v_2018, 2) <> 995804337.00
       OR ROUND(v_2019, 2) <> 1088456509.00
       OR v_award_matches <> 0
       OR v_missing_awards <> 0
    THEN
        RAISE EXCEPTION
            'ETL-210I FAIL: original %, historical mappings %, bad years %, rows %, distinct %, net %, FY18 %, FY19 %, award overrides %, missing awards %',
            v_original_policy,
            v_historical_mappings,
            v_bad_years,
            v_rows,
            v_distinct,
            v_net,
            v_2018,
            v_2019,
            v_award_matches,
            v_missing_awards;
    END IF;

    RAISE NOTICE
        'ETL-210I PASS: SSI FY2018-FY2019 source certified; original policy preserved; no historical mapping or award override';

END $$;

COMMIT;

\echo 'ETL-210I COMPLETE - READ ONLY'