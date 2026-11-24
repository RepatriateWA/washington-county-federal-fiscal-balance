-- ============================================================
-- WCFFBP ETL-210S
-- HISTORICAL MEDICARE POLICY PREFLIGHT
-- FY2018-FY2019: AL 93.773 AND 93.774
--
-- READ ONLY - NO DATABASE WRITES
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-210S - HISTORICAL MEDICARE POLICY PREFLIGHT'
\echo 'AL 93.773 AND 93.774'
\echo 'FY2018-FY2019'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- ============================================================
-- 1. HISTORICAL SOURCE CONTROL
-- ============================================================

\echo ''
\echo '1. HISTORICAL MEDICARE SOURCE CONTROL'

WITH historical AS (
    SELECT
        c.assistance_transaction_id,
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        c.federal_action_obligation AS obligation
    FROM analysis.v_certified_assistance_ledger c
    WHERE BTRIM(c.cfda_number) IN ('93.773', '93.774')
      AND (
           (c.load_batch_id = 20
            AND c.action_date_fiscal_year = 2018)
        OR (c.load_batch_id = 21
            AND c.action_date_fiscal_year = 2019)
      )
)
SELECT
    fiscal_year,
    program_code,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    ROUND(SUM(obligation)::numeric, 2)
        AS net_obligations
FROM historical
GROUP BY fiscal_year, program_code
ORDER BY fiscal_year, program_code;


-- ============================================================
-- 2. EXISTING PROGRAM POLICIES
-- ============================================================

\echo ''
\echo '2. EXISTING MEDICARE PROGRAM POLICIES'

SELECT
    p.source_program_code,
    p.federal_inflow_program_policy_mapping_id
        AS mapping_id,
    p.federal_inflow_source_policy_id
        AS source_policy_id,
    p.resolved_accounting_disposition,
    p.methodology_version,
    p.valid_from_fiscal_year,
    p.valid_through_fiscal_year,
    p.mapping_basis
FROM reference.federal_inflow_program_policy_mapping p
WHERE p.source_system = 'USASPENDING_ASSISTANCE'
  AND BTRIM(p.source_program_code) IN ('93.773', '93.774')
ORDER BY
    p.source_program_code,
    p.valid_from_fiscal_year;


-- ============================================================
-- 3. PREFERRED SOURCE POLICY DETAILS
-- ============================================================

\echo ''
\echo '3. MEDICARE SOURCE POLICY DETAILS'

SELECT
    p.source_program_code,
    s.federal_inflow_source_policy_id,
    s.inflow_family,
    s.inflow_subfamily,
    s.accounting_measure,
    s.preferred_source,
    s.allocation_source,
    s.overlapping_sources,
    s.ledger_treatment,
    s.methodology_version,
    s.valid_from_fiscal_year,
    s.valid_through_fiscal_year,
    s.source_selection_basis
FROM reference.federal_inflow_program_policy_mapping p
JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     p.federal_inflow_source_policy_id
WHERE p.source_system = 'USASPENDING_ASSISTANCE'
  AND BTRIM(p.source_program_code) IN ('93.773', '93.774')
ORDER BY
    p.source_program_code,
    s.valid_from_fiscal_year;


-- ============================================================
-- 4. POLICY COVERAGE BY YEAR
-- ============================================================

\echo ''
\echo '4. POLICY COVERAGE FY2018-FY2025'

WITH years AS (
    SELECT generate_series(2018, 2025) AS fiscal_year
),
programs AS (
    SELECT '93.773'::text AS program_code
    UNION ALL
    SELECT '93.774'::text
)
SELECT
    y.fiscal_year,
    g.program_code,
    COUNT(p.federal_inflow_program_policy_mapping_id)
        AS applicable_mappings,
    STRING_AGG(
        p.resolved_accounting_disposition,
        ', '
        ORDER BY p.federal_inflow_program_policy_mapping_id
    ) AS dispositions
FROM years y
CROSS JOIN programs g
LEFT JOIN reference.federal_inflow_program_policy_mapping p
  ON p.source_system = 'USASPENDING_ASSISTANCE'
 AND BTRIM(p.source_program_code) = g.program_code
 AND y.fiscal_year BETWEEN
     COALESCE(p.valid_from_fiscal_year, -9999)
     AND COALESCE(p.valid_through_fiscal_year, 9999)
GROUP BY y.fiscal_year, g.program_code
ORDER BY y.fiscal_year, g.program_code;


-- ============================================================
-- 5. AWARD-LEVEL CLASSIFICATION COVERAGE
-- ============================================================

\echo ''
\echo '5. HISTORICAL AWARD CLASSIFICATION COVERAGE'

WITH historical AS (
    SELECT
        c.action_date_fiscal_year AS fiscal_year,
        BTRIM(c.cfda_number) AS program_code,
        COALESCE(
            NULLIF(BTRIM(c.award_id_fain), ''),
            NULLIF(BTRIM(c.award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger c
    WHERE BTRIM(c.cfda_number) IN ('93.773', '93.774')
      AND (
           (c.load_batch_id = 20
            AND c.action_date_fiscal_year = 2018)
        OR (c.load_batch_id = 21
            AND c.action_date_fiscal_year = 2019)
      )
)
SELECT
    h.fiscal_year,
    h.program_code,
    COUNT(*) AS source_transactions,
    COUNT(*) FILTER (
        WHERE a.accounting_disposition IS NOT NULL
    ) AS award_classification_matches
FROM historical h
LEFT JOIN reference.federal_inflow_award_classification a
  ON a.source_system = 'USASPENDING_ASSISTANCE'
 AND a.source_program_code = h.program_code
 AND a.source_award_identifier = h.award_identifier
 AND h.fiscal_year BETWEEN
     COALESCE(a.valid_from_fiscal_year, -9999)
     AND COALESCE(a.valid_through_fiscal_year, 9999)
GROUP BY h.fiscal_year, h.program_code
ORDER BY h.fiscal_year, h.program_code;


-- ============================================================
-- 6. CMS DATABASE INVENTORY
-- ============================================================

\echo ''
\echo '6. CMS-RELATED TABLE AND VIEW INVENTORY'

SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema NOT IN (
    'pg_catalog',
    'information_schema'
)
  AND (
      table_schema ILIKE '%cms%'
      OR table_schema ILIKE '%medicare%'
      OR table_name ILIKE '%cms%'
      OR table_name ILIKE '%medicare%'
      OR table_name ILIKE '%trustee%'
      OR table_name ILIKE '%hospital_insurance%'
      OR table_name ILIKE '%supplementary_medical%'
  )
ORDER BY table_schema, table_name;


\echo ''
\echo '7. CMS-RELATED FISCAL-YEAR COLUMN INVENTORY'

SELECT
    c.table_schema,
    c.table_name,
    c.column_name,
    c.data_type
FROM information_schema.columns c
WHERE c.table_schema NOT IN (
    'pg_catalog',
    'information_schema'
)
  AND (
      c.table_schema ILIKE '%cms%'
      OR c.table_schema ILIKE '%medicare%'
      OR c.table_name ILIKE '%cms%'
      OR c.table_name ILIKE '%medicare%'
      OR c.table_name ILIKE '%trustee%'
  )
  AND (
      c.column_name ILIKE '%year%'
      OR c.column_name ILIKE '%fiscal%'
      OR c.column_name ILIKE '%amount%'
      OR c.column_name ILIKE '%payment%'
      OR c.column_name ILIKE '%expenditure%'
  )
ORDER BY
    c.table_schema,
    c.table_name,
    c.ordinal_position;


-- ============================================================
-- 7. HARD CONTROLS
-- ============================================================

\echo ''
\echo '8. AUTOMATED PREFLIGHT CONTROLS'

DO $$
DECLARE
    v_rows bigint;
    v_distinct bigint;
    v_net numeric;

    v_historical_mappings bigint;
    v_award_matches bigint;

    v_original_mappings bigint;
    v_original_bad bigint;
BEGIN

    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),
        COALESCE(SUM(federal_action_obligation), 0)
    INTO v_rows, v_distinct, v_net
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) IN ('93.773', '93.774')
      AND (
           (load_batch_id = 20
            AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21
            AND action_date_fiscal_year = 2019)
      );

    IF v_rows <> 36
       OR v_distinct <> 36
       OR ROUND(v_net, 2) <> 2489730308.00
    THEN
        RAISE EXCEPTION
            'ETL-210S source FAIL: rows %, distinct %, net %',
            v_rows, v_distinct, v_net;
    END IF;

    SELECT COUNT(*)
    INTO v_historical_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND BTRIM(source_program_code) IN ('93.773', '93.774')
      AND COALESCE(valid_from_fiscal_year, -9999) <= 2019
      AND COALESCE(valid_through_fiscal_year, 9999) >= 2018;

    IF v_historical_mappings <> 0 THEN
        RAISE EXCEPTION
            'ETL-210S unexpected historical mappings: %',
            v_historical_mappings;
    END IF;

    SELECT COUNT(*)
    INTO v_award_matches
    FROM analysis.v_certified_assistance_ledger c
    JOIN reference.federal_inflow_award_classification a
      ON a.source_system = 'USASPENDING_ASSISTANCE'
     AND a.source_program_code = BTRIM(c.cfda_number)
     AND a.source_award_identifier = COALESCE(
         NULLIF(BTRIM(c.award_id_fain), ''),
         NULLIF(BTRIM(c.award_id_uri), '')
     )
     AND c.action_date_fiscal_year BETWEEN
         COALESCE(a.valid_from_fiscal_year, -9999)
         AND COALESCE(a.valid_through_fiscal_year, 9999)
    WHERE BTRIM(c.cfda_number) IN ('93.773', '93.774')
      AND (
           (c.load_batch_id = 20
            AND c.action_date_fiscal_year = 2018)
        OR (c.load_batch_id = 21
            AND c.action_date_fiscal_year = 2019)
      );

    IF v_award_matches <> 0 THEN
        RAISE EXCEPTION
            'ETL-210S unexpected award overrides: %',
            v_award_matches;
    END IF;

    SELECT
        COUNT(*),
        COUNT(*) FILTER (
            WHERE p.resolved_accounting_disposition
                  <> 'EXCLUDE_DUPLICATE'
               OR p.valid_from_fiscal_year <> 2020
               OR p.valid_through_fiscal_year <> 2024
               OR s.federal_inflow_source_policy_id IS NULL
        )
    INTO v_original_mappings, v_original_bad
    FROM reference.federal_inflow_program_policy_mapping p
    LEFT JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         p.federal_inflow_source_policy_id
    WHERE p.source_system = 'USASPENDING_ASSISTANCE'
      AND BTRIM(p.source_program_code) IN ('93.773', '93.774');

    IF v_original_mappings <> 2
       OR v_original_bad <> 0
    THEN
        RAISE EXCEPTION
            'ETL-210S original policy FAIL: mappings %, invalid %',
            v_original_mappings, v_original_bad;
    END IF;

    RAISE NOTICE
        'ETL-210S PASS: 36 transactions/$2489730308.00; original Medicare exclusions preserved; zero historical mappings or award overrides';

END $$;

COMMIT;

\echo 'ETL-210S COMPLETE - READ ONLY'