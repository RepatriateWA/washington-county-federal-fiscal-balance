-- ============================================================
-- WCFFBP ETL-210D
-- HISTORICAL SNAP POLICY EXTENSION PREFLIGHT
-- FY2018-FY2019
--
-- READ ONLY - NO DATABASE WRITES
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-210D - HISTORICAL SNAP POLICY PREFLIGHT'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- 1. Relevant policy table definitions

\echo ''
\echo '1. POLICY TABLE COLUMNS'

SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'reference'
  AND table_name IN (
      'federal_inflow_program_policy_mapping',
      'federal_inflow_source_policy',
      'federal_inflow_award_classification'
  )
ORDER BY table_name, ordinal_position;


-- 2. All existing SNAP program mappings

\echo ''
\echo '2. EXISTING SNAP PROGRAM POLICY ROWS'

SELECT
    to_jsonb(p) AS policy_record
FROM reference.federal_inflow_program_policy_mapping p
WHERE p.source_system = 'USASPENDING_ASSISTANCE'
  AND BTRIM(p.source_program_code) = '10.551'
ORDER BY
    p.valid_from_fiscal_year NULLS FIRST,
    p.valid_through_fiscal_year NULLS LAST;


-- 3. Referenced source policies

\echo ''
\echo '3. EXISTING SNAP SOURCE POLICY DETAILS'

SELECT
    to_jsonb(s) AS source_policy_record
FROM reference.federal_inflow_source_policy s
WHERE EXISTS (
    SELECT 1
    FROM reference.federal_inflow_program_policy_mapping p
    WHERE p.federal_inflow_source_policy_id =
          s.federal_inflow_source_policy_id
      AND p.source_system = 'USASPENDING_ASSISTANCE'
      AND BTRIM(p.source_program_code) = '10.551'
);


-- 4. Historical award-level exceptions

\echo ''
\echo '4. HISTORICAL SNAP AWARD CLASSIFICATIONS'

SELECT
    to_jsonb(a) AS award_classification
FROM reference.federal_inflow_award_classification a
WHERE a.source_system = 'USASPENDING_ASSISTANCE'
  AND BTRIM(a.source_program_code) = '10.551'
  AND (
       COALESCE(a.valid_from_fiscal_year, -9999) <= 2019
   AND COALESCE(a.valid_through_fiscal_year, 9999) >= 2018
  );


-- 5. Effective program disposition by fiscal year

\echo ''
\echo '5. SNAP POLICY COVERAGE FY2018-FY2024'

WITH years AS (
    SELECT generate_series(2018, 2024) AS fiscal_year
)
SELECT
    y.fiscal_year,
    COUNT(p.source_program_code) AS matching_policy_rows,
    STRING_AGG(
        p.resolved_accounting_disposition,
        ', '
        ORDER BY p.resolved_accounting_disposition
    ) AS matching_dispositions,
    STRING_AGG(
        p.methodology_version,
        ', '
        ORDER BY p.methodology_version
    ) AS methodology_versions
FROM years y
LEFT JOIN reference.federal_inflow_program_policy_mapping p
  ON p.source_system = 'USASPENDING_ASSISTANCE'
 AND BTRIM(p.source_program_code) = '10.551'
 AND y.fiscal_year BETWEEN
     COALESCE(p.valid_from_fiscal_year, -9999)
     AND COALESCE(p.valid_through_fiscal_year, 9999)
GROUP BY y.fiscal_year
ORDER BY y.fiscal_year;


-- 6. Existing historical SNAP ledger control

\echo ''
\echo '6. FY2018-FY2019 SNAP SOURCE CONTROL'

SELECT
    action_date_fiscal_year AS fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE BTRIM(cfda_number) = '10.551'
  AND (
       (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
  )
GROUP BY action_date_fiscal_year
ORDER BY fiscal_year;


-- 7. Hard controls

\echo ''
\echo '7. PREFLIGHT SOURCE ASSERTIONS'

DO $$
DECLARE
    v_count bigint;
    v_distinct bigint;
    v_net numeric;
BEGIN
    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),
        COALESCE(SUM(federal_action_obligation), 0)
    INTO v_count, v_distinct, v_net
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) = '10.551'
      AND (
           (load_batch_id = 20
            AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21
            AND action_date_fiscal_year = 2019)
      );

    IF v_count <> 27
       OR v_distinct <> 27
       OR ROUND(v_net, 2) <> 2461253053.11
    THEN
        RAISE EXCEPTION
            'ETL-210D source control failed: rows %, distinct %, net %',
            v_count, v_distinct, v_net;
    END IF;

    RAISE NOTICE
        'ETL-210D PREFLIGHT PASS: 27 historical SNAP transactions, $2461253053.11 net';
END $$;

COMMIT;

\echo 'ETL-210D PREFLIGHT COMPLETE - READ ONLY'