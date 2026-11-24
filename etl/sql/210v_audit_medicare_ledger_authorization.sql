-- ============================================================
-- WCFFBP ETL-210V
-- MEDICARE LEDGER AUTHORIZATION AND ACCOUNTING-BASIS AUDIT
--
-- Historical focus: FY2018-FY2019
-- Policy context:   FY2018-FY2025
--
-- Questions:
--   1. What Medicare ledger/reporting objects exist?
--   2. Which Medicare source policies are effective?
--   3. Are CMS-native Medicare records ledger-authorized?
--   4. What timing and completeness restrictions remain?
--   5. Are historical USAspending Medicare obligations
--      currently classified?
--   6. What evidence is needed before policy migration?
--
-- READ ONLY - NO DATABASE WRITES
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-210V - MEDICARE LEDGER AUTHORIZATION AUDIT'
\echo 'FY2018-FY2019'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- ============================================================
-- 1. MEDICARE AND FEDERAL INFLOW LEDGER OBJECT DISCOVERY
-- ============================================================

\echo ''
\echo '1. MEDICARE AND FEDERAL INFLOW LEDGER OBJECTS'

SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    CASE c.relkind
        WHEN 'r' THEN 'TABLE'
        WHEN 'p' THEN 'PARTITIONED TABLE'
        WHEN 'v' THEN 'VIEW'
        WHEN 'm' THEN 'MATERIALIZED VIEW'
        ELSE c.relkind::text
    END AS object_type
FROM pg_class c
JOIN pg_namespace n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p', 'v', 'm')
  AND n.nspname NOT IN (
      'pg_catalog',
      'information_schema'
  )
  AND n.nspname NOT LIKE 'pg_toast%'
  AND (
       c.relname ILIKE '%medicare%'
    OR c.relname ILIKE '%federal_inflow%'
    OR c.relname ILIKE '%ledger%'
    OR c.relname ILIKE '%balance%'
  )
ORDER BY
    n.nspname,
    c.relname;


-- ============================================================
-- 2. POTENTIAL LEDGER AUTHORIZATION FIELDS
-- ============================================================

\echo ''
\echo '2. LEDGER AUTHORIZATION AND ACCOUNTING FIELDS'

SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema NOT IN (
    'pg_catalog',
    'information_schema'
)
  AND (
       table_name ILIKE '%medicare%'
    OR table_name ILIKE '%ledger%'
    OR table_name ILIKE '%federal_inflow%'
    OR table_name ILIKE '%balance%'
  )
  AND (
       column_name ILIKE '%authoriz%'
    OR column_name ILIKE '%ledger%'
    OR column_name ILIKE '%disposition%'
    OR column_name ILIKE '%status%'
    OR column_name ILIKE '%fiscal_year%'
    OR column_name ILIKE '%calendar_year%'
    OR column_name ILIKE '%report_year%'
    OR column_name ILIKE '%source%'
    OR column_name ILIKE '%timing%'
    OR column_name ILIKE '%accounting%'
    OR column_name ILIKE '%methodology%'
  )
ORDER BY
    table_schema,
    table_name,
    ordinal_position;


-- ============================================================
-- 3. MEDICARE SOURCE POLICY INVENTORY
-- ============================================================

\echo ''
\echo '3. MEDICARE SOURCE POLICIES'

SELECT
    federal_inflow_source_policy_id,
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE inflow_family = 'MEDICARE'
ORDER BY
    inflow_subfamily,
    valid_from_fiscal_year,
    federal_inflow_source_policy_id;


-- ============================================================
-- 4. HISTORICAL MEDICARE PROGRAM MAPPINGS
-- ============================================================

\echo ''
\echo '4. USAspending MEDICARE PROGRAM MAPPINGS'

SELECT
    federal_inflow_program_policy_mapping_id,
    federal_inflow_source_policy_id,
    source_system,
    source_program_code,
    resolved_accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND BTRIM(source_program_code)
      IN ('93.773', '93.774')
ORDER BY
    source_program_code,
    valid_from_fiscal_year;


-- ============================================================
-- 5. YEAR-BY-YEAR POLICY COVERAGE
-- ============================================================

\echo ''
\echo '5. MEDICARE POLICY COVERAGE FY2018-FY2025'

WITH years AS (
    SELECT generate_series(2018, 2025)
        AS fiscal_year
),
programs AS (
    SELECT '93.773'::text AS program_code
    UNION ALL
    SELECT '93.774'::text
)
SELECT
    y.fiscal_year,
    p.program_code,
    COUNT(m.federal_inflow_program_policy_mapping_id)
        AS applicable_mappings,
    STRING_AGG(
        m.resolved_accounting_disposition,
        '; ' ORDER BY
        m.federal_inflow_program_policy_mapping_id
    ) AS dispositions,
    COUNT(*) FILTER (
        WHERE m.federal_inflow_program_policy_mapping_id
              IS NOT NULL
          AND (
               s.federal_inflow_source_policy_id IS NULL
            OR y.fiscal_year <
               COALESCE(s.valid_from_fiscal_year, -9999)
            OR y.fiscal_year >
               COALESCE(s.valid_through_fiscal_year, 9999)
          )
    ) AS source_policy_period_mismatches
FROM years y
CROSS JOIN programs p
LEFT JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND BTRIM(m.source_program_code) = p.program_code
 AND y.fiscal_year BETWEEN
     COALESCE(m.valid_from_fiscal_year, -9999)
     AND
     COALESCE(m.valid_through_fiscal_year, 9999)
LEFT JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
GROUP BY
    y.fiscal_year,
    p.program_code
ORDER BY
    y.fiscal_year,
    p.program_code;


-- ============================================================
-- 6. CMS STATEWIDE LEDGER AUTHORIZATION
-- ============================================================

\echo ''
\echo '6. CMS STATEWIDE MEDICARE LEDGER AUTHORIZATION'

SELECT
    calendar_year,
    state_id,
    ROUND(
        original_medicare_actual_ffs_dollars::numeric,
        2
    ) AS original_medicare_ffs,
    ROUND(
        partc_reconstructed_dollars::numeric,
        2
    ) AS partc_reconstructed,
    ROUND(
        partd_reconstructed_dollars::numeric,
        2
    ) AS partd_reconstructed,
    ROUND(
        core_medicare_sum_dollars::numeric,
        2
    ) AS core_medicare_total,
    partc_months_processed,
    partc_year_completeness,
    partc_reconstruction_coverage_pct,
    partc_accounting_coverage_pct,
    partd_coverage_status,
    combined_period_status,
    timing_basis_status,
    ledger_status,
    methodology_version
FROM cms.medicare_core_state_year
WHERE calendar_year BETWEEN 2018 AND 2025
ORDER BY
    calendar_year,
    state_id;


-- ============================================================
-- 7. COUNTY AUTHORIZATION SUMMARY
-- ============================================================

\echo ''
\echo '7. CMS COUNTY LEDGER AUTHORIZATION SUMMARY'

SELECT
    calendar_year,
    ledger_authorization,
    core_value_status,
    partc_status,
    partd_coverage_status,
    time_window_status,
    timing_basis,
    COUNT(*) AS county_rows,
    COUNT(*) FILTER (
        WHERE core_medicare_dollars IS NULL
    ) AS withheld_core_values,
    ROUND(
        SUM(core_medicare_dollars)::numeric,
        2
    ) AS available_core_dollars
FROM cms.medicare_core_county_year
WHERE calendar_year BETWEEN 2018 AND 2025
GROUP BY
    calendar_year,
    ledger_authorization,
    core_value_status,
    partc_status,
    partd_coverage_status,
    time_window_status,
    timing_basis
ORDER BY
    calendar_year,
    county_rows DESC;


-- ============================================================
-- 8. MEDICARE GEOGRAPHIC PAYMENT CONTROL
-- ============================================================

\echo ''
\echo '8. CMS GEOGRAPHIC PAYMENT CONTROL'

SELECT
    report_year,
    state_id,
    COUNT(*) AS geographic_rows,
    COUNT(DISTINCT county_id) AS counties,
    ROUND(
        SUM(total_medicare_payments_dollars)::numeric,
        2
    ) AS actual_payment_dollars,
    ROUND(
        SUM(
            standardized_medicare_payments_dollars
        )::numeric,
        2
    ) AS standardized_payment_dollars
FROM cms.medicare_geographic_payments
WHERE report_year BETWEEN 2018 AND 2025
GROUP BY
    report_year,
    state_id
ORDER BY
    report_year,
    state_id;


-- ============================================================
-- 9. HISTORICAL USASPENDING MEDICARE OBLIGATIONS
-- ============================================================

\echo ''
\echo '9. HISTORICAL USASPENDING MEDICARE SOURCE CONTROL'

SELECT
    action_date_fiscal_year AS fiscal_year,
    BTRIM(cfda_number) AS program_code,
    COUNT(*) AS transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE BTRIM(cfda_number) IN ('93.773', '93.774')
  AND (
       (load_batch_id = 20
        AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21
        AND action_date_fiscal_year = 2019)
  )
GROUP BY
    action_date_fiscal_year,
    BTRIM(cfda_number)
ORDER BY
    fiscal_year,
    program_code;


-- ============================================================
-- 10. EXISTING MEDICARE LEDGER VIEW DEFINITIONS
--
-- Inventory only: these definitions help identify
-- possible accounting paths, but do not prove that
-- any source is authorized or included.
-- ============================================================

\echo ''
\echo '10. MEDICARE AND INFLOW LEDGER VIEW DEFINITIONS'

SELECT
    schemaname,
    viewname,
    LEFT(definition, 6000)
        AS definition_excerpt
FROM pg_views
WHERE schemaname IN (
    'analysis',
    'reporting',
    'cms'
)
  AND (
       viewname ILIKE '%medicare%'
    OR viewname ILIKE '%federal_inflow%'
    OR viewname ILIKE '%balance%'
  )
ORDER BY
    schemaname,
    viewname;


-- ============================================================
-- 11. HISTORICAL AWARD OVERRIDE COVERAGE
-- ============================================================

\echo ''
\echo '11. HISTORICAL MEDICARE AWARD OVERRIDES'

SELECT
    source_program_code,
    accounting_disposition,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    COUNT(*) AS override_records
FROM reference.federal_inflow_award_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND BTRIM(source_program_code)
      IN ('93.773', '93.774')
  AND COALESCE(valid_from_fiscal_year, -9999)
      <= 2019
  AND COALESCE(valid_through_fiscal_year, 9999)
      >= 2018
GROUP BY
    source_program_code,
    accounting_disposition,
    valid_from_fiscal_year,
    valid_through_fiscal_year
ORDER BY
    source_program_code,
    accounting_disposition;


-- ============================================================
-- 12. AUTOMATED CONSERVATION AND NON-MUTATION GATES
-- ============================================================

\echo ''
\echo '12. AUTOMATED AUDIT CONTROLS'

DO $$
DECLARE
    v_source_rows bigint;
    v_distinct_rows bigint;
    v_source_dollars numeric;
    v_state_rows bigint;
    v_county_rows bigint;
    v_historical_mappings bigint;
    v_historical_overrides bigint;
    v_unauthorized_state_rows bigint;
BEGIN

    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),
        COALESCE(SUM(federal_action_obligation), 0)
    INTO
        v_source_rows,
        v_distinct_rows,
        v_source_dollars
    FROM analysis.v_certified_assistance_ledger
    WHERE BTRIM(cfda_number) IN ('93.773', '93.774')
      AND (
           (load_batch_id = 20
            AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21
            AND action_date_fiscal_year = 2019)
      );

    SELECT COUNT(*)
    INTO v_state_rows
    FROM cms.medicare_core_state_year
    WHERE calendar_year IN (2018, 2019);

    SELECT COUNT(*)
    INTO v_county_rows
    FROM cms.medicare_core_county_year
    WHERE calendar_year IN (2018, 2019);

    SELECT COUNT(*)
    INTO v_historical_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND BTRIM(source_program_code)
          IN ('93.773', '93.774')
      AND COALESCE(valid_from_fiscal_year, -9999)
          <= 2019
      AND COALESCE(valid_through_fiscal_year, 9999)
          >= 2018;

    SELECT COUNT(*)
    INTO v_historical_overrides
    FROM reference.federal_inflow_award_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND BTRIM(source_program_code)
          IN ('93.773', '93.774')
      AND COALESCE(valid_from_fiscal_year, -9999)
          <= 2019
      AND COALESCE(valid_through_fiscal_year, 9999)
          >= 2018;

    SELECT COUNT(*)
    INTO v_unauthorized_state_rows
    FROM cms.medicare_core_state_year
    WHERE calendar_year IN (2018, 2019)
      AND ledger_status = 'NOT_YET_AUTHORIZED';

    IF v_source_rows <> 36
       OR v_distinct_rows <> 36
       OR ROUND(v_source_dollars, 2)
          <> 2489730308.00
       OR v_state_rows <> 2
       OR v_county_rows <> 78
       OR v_historical_mappings <> 0
       OR v_historical_overrides <> 0
       OR v_unauthorized_state_rows <> 2
    THEN
        RAISE EXCEPTION
            'ETL-210V FAIL: source %, distinct %, dollars %, state %, county %, mappings %, overrides %, unauthorized state %',
            v_source_rows,
            v_distinct_rows,
            v_source_dollars,
            v_state_rows,
            v_county_rows,
            v_historical_mappings,
            v_historical_overrides,
            v_unauthorized_state_rows;
    END IF;

    RAISE NOTICE
        'ETL-210V STRUCTURAL PASS: historical Medicare sources and policy state conserved';

    RAISE NOTICE
        'CMS STATEWIDE CORE 2018-2019: NOT_YET_AUTHORIZED';

    RAISE NOTICE
        'NO HISTORICAL MEDICARE CLASSIFICATION OR LEDGER WRITE AUTHORIZED BY THIS AUDIT';

END $$;

COMMIT;

\echo 'ETL-210V COMPLETE - READ ONLY'