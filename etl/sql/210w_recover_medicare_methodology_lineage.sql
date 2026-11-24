-- ============================================================
-- WCFFBP ETL-210W
-- MEDICARE METHODOLOGY RECOVERY AND LINEAGE AUDIT
--
-- Focus: Reuse FY2020-2024 Medicare methodology
--        for FY2018-2019 historical reconciliation.
--
-- RULES:
-- 1. No double counting.
-- 2. No unsupported fiscal-year conversions.
-- 3. No new ledger authorizations without evidence.
--
-- READ ONLY - NO DATABASE WRITES
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-210W - MEDICARE METHODOLOGY AND LINEAGE'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

-- ============================================================
-- 1. DISCOVER MEDICARE-RELATED DATABASE OBJECTS
-- ============================================================

\echo ''
\echo '1. MEDICARE-RELATED DATABASE OBJECTS'

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
    OR c.relname ILIKE '%mssp%'
    OR c.relname ILIKE '%partc%'
    OR c.relname ILIKE '%partd%'
    OR c.relname ILIKE '%tracked_expenditure%'
    OR c.relname ILIKE '%fiscal_balance%'
  )
ORDER BY
    n.nspname,
    c.relname;


-- ============================================================
-- 2. DISCOVER SOURCE, VALIDATION, AND POLICY METADATA
-- ============================================================

\echo ''
\echo '2. SOURCE AND VALIDATION METADATA OBJECTS'

SELECT
    table_schema,
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema NOT IN (
    'pg_catalog',
    'information_schema'
)
  AND (
       table_name ILIKE '%medicare%'
    OR table_name ILIKE '%mssp%'
    OR table_name ILIKE '%partc%'
    OR table_name ILIKE '%partd%'
  )
  AND (
       column_name ILIKE '%source%'
    OR column_name ILIKE '%sha256%'
    OR column_name ILIKE '%methodology%'
    OR column_name ILIKE '%status%'
    OR column_name ILIKE '%coverage%'
    OR column_name ILIKE '%timing%'
    OR column_name ILIKE '%authoriz%'
    OR column_name ILIKE '%year%'
  )
ORDER BY
    table_schema,
    table_name,
    ordinal_position;


-- ============================================================
-- 3. MEDICARE SOURCE POLICY LINEAGE
-- ============================================================

\echo ''
\echo '3. MEDICARE SOURCE POLICY LINEAGE'

SELECT
    federal_inflow_source_policy_id,
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
FROM reference.federal_inflow_source_policy
WHERE inflow_family = 'MEDICARE'
ORDER BY
    inflow_subfamily,
    valid_from_fiscal_year;


-- ============================================================
-- 4. USASPENDING MEDICARE POLICY MAPPINGS
-- ============================================================

\echo ''
\echo '4. MEDICARE PROGRAM POLICY MAPPINGS'

SELECT
    federal_inflow_program_policy_mapping_id,
    federal_inflow_source_policy_id,
    source_system,
    source_program_code,
    resolved_accounting_disposition,
    mapping_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping
WHERE federal_inflow_source_policy_id IN (
    SELECT federal_inflow_source_policy_id
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'MEDICARE'
)
ORDER BY
    source_program_code,
    valid_from_fiscal_year;


-- ============================================================
-- 5. CMS CORE STATE ACCOUNTING PROVENANCE
-- ============================================================

\echo ''
\echo '5. CMS STATE ACCOUNTING PROVENANCE'

SELECT
    calendar_year,
    state_id,
    ROUND(
        original_medicare_actual_ffs_dollars::numeric,
        2
    ) AS original_ffs,
    ROUND(
        partc_reconstructed_dollars::numeric,
        2
    ) AS partc,
    ROUND(
        partd_reconstructed_dollars::numeric,
        2
    ) AS partd,
    ROUND(
        core_medicare_sum_dollars::numeric,
        2
    ) AS reconstructed_core,
    partc_months_processed,
    partc_year_completeness,
    partd_dollar_source_field,
    partd_coverage_status,
    combined_period_status,
    timing_basis_status,
    ledger_status,
    methodology_version,
    source_file,
    source_sha256
FROM cms.medicare_core_state_year
WHERE calendar_year BETWEEN 2018 AND 2024
ORDER BY calendar_year;


-- ============================================================
-- 6. COUNTY COMPONENT RECONSTRUCTION STATUS
-- ============================================================

\echo ''
\echo '6. COUNTY MEDICARE RECONSTRUCTION STATUS'

SELECT
    calendar_year,
    original_medicare_status,
    partc_status,
    partd_status,
    core_value_status,
    partc_year_completeness,
    partd_coverage_status,
    time_window_status,
    ledger_authorization,
    methodology_version,
    COUNT(*) AS county_rows,
    COUNT(*) FILTER (
        WHERE core_medicare_dollars IS NULL
    ) AS withheld_core_rows
FROM cms.medicare_core_county_year
WHERE calendar_year BETWEEN 2018 AND 2024
GROUP BY
    calendar_year,
    original_medicare_status,
    partc_status,
    partd_status,
    core_value_status,
    partc_year_completeness,
    partd_coverage_status,
    time_window_status,
    ledger_authorization,
    methodology_version
ORDER BY
    calendar_year,
    county_rows DESC;


-- ============================================================
-- 7. SOURCE FILE AND HASH DISTRIBUTION
-- ============================================================

\echo ''
\echo '7. CMS SOURCE FILE AND HASH DISTRIBUTION'

SELECT
    calendar_year,
    source_file,
    source_sha256,
    methodology_version,
    COUNT(*) AS county_rows
FROM cms.medicare_core_county_year
WHERE calendar_year BETWEEN 2018 AND 2024
GROUP BY
    calendar_year,
    source_file,
    source_sha256,
    methodology_version
ORDER BY
    calendar_year,
    county_rows DESC;


-- ============================================================
-- 8. REPORTING VIEW DEFINITIONS
--
-- These reveal the SQL accounting path.
-- They do not independently certify ledger inclusion.
-- ============================================================

\echo ''
\echo '8. TRACKED EXPENDITURE AND BALANCE VIEW DEFINITIONS'

SELECT
    schemaname,
    viewname,
    definition
FROM pg_views
WHERE schemaname = 'reporting'
  AND viewname IN (
      'v_washington_tracked_expenditures',
      'v_washington_partial_fiscal_balance',
      'v_medicare_expenditures_by_state_year',
      'v_medicare_expenditures_by_county_year'
  )
ORDER BY viewname;


-- ============================================================
-- 9. REPORTING VIEW DEPENDENCIES
--
-- Direct PostgreSQL dependencies only.
-- ============================================================

\echo ''
\echo '9. DIRECT REPORTING VIEW DEPENDENCIES'

SELECT DISTINCT
    source_ns.nspname AS source_schema,
    source.relname AS source_view,
    target_ns.nspname AS dependency_schema,
    target.relname AS dependency_object,
    CASE target.relkind
        WHEN 'r' THEN 'TABLE'
        WHEN 'p' THEN 'PARTITIONED TABLE'
        WHEN 'v' THEN 'VIEW'
        WHEN 'm' THEN 'MATERIALIZED VIEW'
        ELSE target.relkind::text
    END AS dependency_type
FROM pg_class source
JOIN pg_namespace source_ns
  ON source_ns.oid = source.relnamespace
JOIN pg_rewrite rewrite
  ON rewrite.ev_class = source.oid
JOIN pg_depend dependency
  ON dependency.objid = rewrite.oid
JOIN pg_class target
  ON target.oid = dependency.refobjid
JOIN pg_namespace target_ns
  ON target_ns.oid = target.relnamespace
WHERE source_ns.nspname = 'reporting'
  AND source.relname IN (
      'v_washington_tracked_expenditures',
      'v_washington_partial_fiscal_balance',
      'v_medicare_expenditures_by_state_year',
      'v_medicare_expenditures_by_county_year'
  )
  AND target.oid <> source.oid
ORDER BY
    source_schema,
    source_view,
    dependency_schema,
    dependency_object;


-- ============================================================
-- 10. TRACKED EXPENDITURE VIEW SCHEMA
-- ============================================================

\echo ''
\echo '10. TRACKED EXPENDITURE VIEW COLUMNS'

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'reporting'
  AND table_name = 'v_washington_tracked_expenditures'
ORDER BY ordinal_position;


-- ============================================================
-- 11. MEDICARE POLICY COVERAGE BY YEAR
-- ============================================================

\echo ''
\echo '11. HISTORICAL MEDICARE POLICY COVERAGE'

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
        AS matching_mappings,
    STRING_AGG(
        m.resolved_accounting_disposition,
        '; '
    ) AS accounting_dispositions
FROM years y
CROSS JOIN programs p
LEFT JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system = 'USASPENDING_ASSISTANCE'
 AND BTRIM(m.source_program_code) = p.program_code
 AND y.fiscal_year BETWEEN
     COALESCE(m.valid_from_fiscal_year, -9999)
     AND
     COALESCE(m.valid_through_fiscal_year, 9999)
GROUP BY
    y.fiscal_year,
    p.program_code
ORDER BY
    y.fiscal_year,
    p.program_code;


-- ============================================================
-- 12. AUTOMATED READ-ONLY STRUCTURAL GATES
-- ============================================================

\echo ''
\echo '12. AUTOMATED STRUCTURAL CONTROLS'

DO $$
DECLARE
    v_state_rows bigint;
    v_county_rows bigint;
    v_historical_unauthorized bigint;
    v_reporting_view_exists boolean;
BEGIN

    SELECT COUNT(*)
    INTO v_state_rows
    FROM cms.medicare_core_state_year
    WHERE calendar_year BETWEEN 2018 AND 2024;

    SELECT COUNT(*)
    INTO v_county_rows
    FROM cms.medicare_core_county_year
    WHERE calendar_year BETWEEN 2018 AND 2024;

    SELECT COUNT(*)
    INTO v_historical_unauthorized
    FROM cms.medicare_core_state_year
    WHERE calendar_year IN (2018, 2019)
      AND ledger_status = 'NOT_YET_AUTHORIZED';

    SELECT EXISTS (
        SELECT 1
        FROM pg_views
        WHERE schemaname = 'reporting'
          AND viewname =
              'v_washington_tracked_expenditures'
    )
    INTO v_reporting_view_exists;

    IF v_state_rows <> 7
       OR v_county_rows <> 273
       OR v_historical_unauthorized <> 2
       OR NOT v_reporting_view_exists
    THEN
        RAISE EXCEPTION
            'ETL-210W FAIL: state %, county %, historical unauthorized %, reporting view %',
            v_state_rows,
            v_county_rows,
            v_historical_unauthorized,
            v_reporting_view_exists;
    END IF;

    RAISE NOTICE
        'ETL-210W STRUCTURAL PASS: Medicare source inventory and historical authorization status conserved';

    RAISE NOTICE
        'NO LEDGER INCLUSION OR FISCAL-YEAR CONVERSION AUTHORIZED';

END $$;

COMMIT;

\echo 'ETL-210W COMPLETE - READ ONLY'